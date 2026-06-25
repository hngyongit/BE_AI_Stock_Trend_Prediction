const FactCrawlQuality = require('../../database/models/fact-crawl-quality.model');
const CrawlLogDetail = require('../../database/models/crawl-log-detail.model');
const DimStock = require('../../database/models/dim-stock.model');

/**
 * Get the quality dashboard summary
 */
const getQualityDashboard = async () => {
    // Overall aggregates from FactCrawlQuality
    const qualityAgg = await FactCrawlQuality.aggregate([
        {
            $group: {
                _id: null,
                total_fetched: { $sum: '$records_fetched' },
                total_inserted: { $sum: '$records_inserted' },
                total_updated: { $sum: '$records_updated' },
                total_failed: { $sum: '$records_failed' },
                avg_success_rate: { $avg: '$success_rate' },
                count: { $sum: 1 }
            }
        }
    ]);

    // Worst source (by lowest avg success rate)
    const worstSource = await FactCrawlQuality.aggregate([
        {
            $group: {
                _id: '$data_source_id',
                avg_success_rate: { $avg: '$success_rate' },
                total_failed: { $sum: '$records_failed' },
                runs: { $sum: 1 }
            }
        },
        { $sort: { avg_success_rate: 1 } },
        { $limit: 1 },
        {
            $lookup: {
                from: 'dimDataSources',
                localField: '_id',
                foreignField: '_id',
                as: 'source'
            }
        },
        { $unwind: { path: '$source', preserveNullAndEmptyArrays: true } }
    ]);

    // Recent quality trends (last 7 days)
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const today = new Date();
    today.setHours(23, 59, 59, 999);

    const recentTrends = await FactCrawlQuality.aggregate([
        {
            $match: {
                created_at: { $gte: sevenDaysAgo }
            }
        },
        {
            $group: {
                _id: { $dateToString: { format: '%Y-%m-%d', date: '$created_at' } },
                avg_success_rate: { $avg: '$success_rate' },
                total_failed: { $sum: '$records_failed' },
                runs: { $sum: 1 }
            }
        },
        { $sort: { _id: 1 } }
    ]);

    // Total failed symbols across all logs
    const totalFailedSymbols = await CrawlLogDetail.countDocuments({ status: 'FAILED' });

    const overall = qualityAgg[0] || {
        total_fetched: 0,
        total_inserted: 0,
        total_updated: 0,
        total_failed: 0,
        avg_success_rate: 0,
        count: 0
    };

    return {
        overall: {
            total_runs: overall.count,
            records_fetched: overall.total_fetched,
            records_inserted: overall.total_inserted,
            records_updated: overall.total_updated,
            records_failed: overall.total_failed,
            avg_success_rate_percent: Number((overall.avg_success_rate || 0).toFixed(2))
        },
        worst_source: worstSource[0] ? {
            source_id: worstSource[0]._id.toString(),
            source_name: worstSource[0].source?.name || 'Unknown',
            avg_success_rate: Number((worstSource[0].avg_success_rate || 0).toFixed(2)),
            total_failed: worstSource[0].total_failed,
            runs: worstSource[0].runs
        } : null,
        total_failed_symbols: totalFailedSymbols,
        recent_trends: recentTrends.map(t => ({
            date: t._id,
            avg_success_rate: Number((t.avg_success_rate || 0).toFixed(2)),
            total_failed: t.total_failed,
            runs: t.runs
        }))
    };
};

/**
 * Get quality metrics grouped by data source
 */
const getQualityBySource = async () => {
    const result = await FactCrawlQuality.aggregate([
        {
            $group: {
                _id: '$data_source_id',
                avg_success_rate: { $avg: '$success_rate' },
                total_fetched: { $sum: '$records_fetched' },
                total_inserted: { $sum: '$records_inserted' },
                total_updated: { $sum: '$records_updated' },
                total_failed: { $sum: '$records_failed' },
                runs: { $sum: 1 }
            }
        },
        {
            $lookup: {
                from: 'dimDataSources',
                localField: '_id',
                foreignField: '_id',
                as: 'source'
            }
        },
        { $unwind: { path: '$source', preserveNullAndEmptyArrays: true } },
        { $sort: { avg_success_rate: 1 } }
    ]);

    return result.map(r => ({
        source_id: r._id.toString(),
        source_name: r.source?.name || 'Unknown',
        source_type: r.source?.provider_type || 'N/A',
        avg_success_rate_percent: Number((r.avg_success_rate || 0).toFixed(2)),
        records_fetched: r.total_fetched,
        records_inserted: r.total_inserted,
        records_updated: r.total_updated,
        records_failed: r.total_failed,
        runs: r.runs
    }));
};

/**
 * Get quality metrics grouped by crawl job
 */
const getQualityByJob = async () => {
    const result = await FactCrawlQuality.aggregate([
        {
            $group: {
                _id: '$crawl_job_id',
                avg_success_rate: { $avg: '$success_rate' },
                total_fetched: { $sum: '$records_fetched' },
                total_inserted: { $sum: '$records_inserted' },
                total_updated: { $sum: '$records_updated' },
                total_failed: { $sum: '$records_failed' },
                runs: { $sum: 1 }
            }
        },
        {
            $lookup: {
                from: 'crawlJobs',
                localField: '_id',
                foreignField: '_id',
                as: 'job'
            }
        },
        { $unwind: { path: '$job', preserveNullAndEmptyArrays: true } },
        { $sort: { avg_success_rate: 1 } }
    ]);

    return result.map(r => ({
        job_id: r._id ? r._id.toString() : null,
        job_name: r.job?.job_name || 'Unknown/Deleted Job',
        data_type: r.job?.data_type || 'N/A',
        avg_success_rate_percent: Number((r.avg_success_rate || 0).toFixed(2)),
        records_fetched: r.total_fetched,
        records_inserted: r.total_inserted,
        records_updated: r.total_updated,
        records_failed: r.total_failed,
        runs: r.runs
    }));
};

/**
 * Detect stocks with no data for a given date range
 */
const getMissingRecords = async (queries) => {
    const dateFrom = queries.date_from || new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const dateTo = queries.date_to || new Date();

    const fromDate = new Date(dateFrom);
    const toDate = new Date(dateTo);

    const fromTimeId = parseInt(
        `${fromDate.getFullYear()}${String(fromDate.getMonth() + 1).padStart(2, '0')}${String(fromDate.getDate()).padStart(2, '0')}`,
        10
    );
    const toTimeId = parseInt(
        `${toDate.getFullYear()}${String(toDate.getMonth() + 1).padStart(2, '0')}${String(toDate.getDate()).padStart(2, '0')}`,
        10
    );

    // Get active stocks
    const totalStocks = await DimStock.countDocuments({ status: 'ACTIVE' });

    // Get stocks that have data in the range (via FactCrawlQuality or just aggregate)
    const successRecords = await FactCrawlQuality.aggregate([
        {
            $match: {
                time_id: { $gte: fromTimeId, $lte: toTimeId },
                status: { $in: ['SUCCESS', 'PARTIAL_SUCCESS'] }
            }
        },
        {
            $group: {
                _id: null,
                records_inserted: { $sum: '$records_inserted' },
                records_updated: { $sum: '$records_updated' },
                records_failed: { $sum: '$records_failed' }
            }
        }
    ]);

    // Get failed symbols count in the range
    const failedInRange = await CrawlLogDetail.countDocuments({
        status: 'FAILED',
        created_at: { $gte: fromDate, $lte: toDate }
    });

    const summary = successRecords[0] || { records_inserted: 0, records_updated: 0, records_failed: 0 };

    return {
        date_range: {
            from: fromDate.toISOString().split('T')[0],
            to: toDate.toISOString().split('T')[0]
        },
        total_active_stocks: totalStocks,
        records_inserted: summary.records_inserted,
        records_updated: summary.records_updated,
        records_failed: summary.records_failed,
        failed_symbols_in_range: failedInRange
    };
};

module.exports = {
    getQualityDashboard,
    getQualityBySource,
    getQualityByJob,
    getMissingRecords
};