const CrawlLog = require('../../database/models/crawl-log.model');
const CrawlLogDetail = require('../../database/models/crawl-log-detail.model');

/**
 * Staff: Get paginated list of crawl logs (filterable, read-only)
 */
const listCrawlLogs = async (queries) => {
    const page = parseInt(queries.page || '1', 10);
    const limit = parseInt(queries.limit || '20', 10);
    const skip = (page - 1) * limit;

    const filter = {};

    // Filter by crawl job
    if (queries.crawl_job_id) {
        filter.crawl_job_id = queries.crawl_job_id;
    }

    // Filter by status
    if (queries.status) {
        filter.status = queries.status;
    }

    // Filter by date range
    if (queries.date_from || queries.date_to) {
        filter.started_at = {};
        if (queries.date_from) {
            filter.started_at.$gte = new Date(queries.date_from);
        }
        if (queries.date_to) {
            filter.started_at.$lte = new Date(queries.date_to);
        }
    }

    // Sort
    const sortField = queries.sort_by || 'started_at';
    const sortOrder = queries.sort_order === 'asc' ? 1 : -1;

    const items = await CrawlLog.find(filter)
        .populate({
            path: 'crawl_job_id',
            select: 'job_name data_type'
        })
        .sort({ [sortField]: sortOrder })
        .skip(skip)
        .limit(limit);

    const total_items = await CrawlLog.countDocuments(filter);
    const total_pages = Math.ceil(total_items / limit);

    return {
        items,
        pagination: { page, limit, total_items, total_pages }
    };
};

/**
 * Staff: Get a single crawl log with all its detail records
 */
const getCrawlLogDetail = async (id) => {
    const log = await CrawlLog.findById(id)
        .populate({
            path: 'crawl_job_id',
            select: 'job_name data_type'
        });

    if (!log) {
        const error = new Error('Crawl log not found');
        error.statusCode = 404;
        throw error;
    }

    // Fetch all detail records for this log
    const details = await CrawlLogDetail.find({ crawl_log_id: id })
        .populate({
            path: 'stock_id',
            select: 'symbol company_name'
        })
        .sort({ status: 1, symbol: 1 });

    return { log, details };
};

/**
 * Staff: Get details by symbol within a crawl log
 */
const getDetailBySymbol = async (logId, symbol) => {
    const log = await CrawlLog.findById(logId);
    if (!log) {
        const error = new Error('Crawl log not found');
        error.statusCode = 404;
        throw error;
    }

    const details = await CrawlLogDetail.find({
        crawl_log_id: logId,
        symbol: { $regex: symbol, $options: 'i' }
    }).populate({
        path: 'stock_id',
        select: 'symbol company_name'
    });

    return { log, details };
};

/**
 * Staff: Get all FAILED details across logs (optionally filtered by crawl_job_id)
 */
const getFailedSymbols = async (queries) => {
    const filter = { status: 'FAILED' };

    if (queries.crawl_job_id) {
        // Find log IDs for this job, then filter details
        const logIds = await CrawlLog.find({ crawl_job_id: queries.crawl_job_id }).distinct('_id');
        filter.crawl_log_id = { $in: logIds };
    }

    if (queries.limit) {
        const limit = parseInt(queries.limit, 10);
        const details = await CrawlLogDetail.find(filter)
            .populate({
                path: 'stock_id',
                select: 'symbol company_name'
            })
            .populate({
                path: 'crawl_log_id',
                select: 'started_at status'
            })
            .sort({ created_at: -1 })
            .limit(limit);

        return { items: details, total: details.length };
    }

    const details = await CrawlLogDetail.find(filter)
        .populate({
            path: 'stock_id',
            select: 'symbol company_name'
        })
        .populate({
            path: 'crawl_log_id',
            select: 'started_at status'
        })
        .sort({ created_at: -1 });

    return { items: details, total: details.length };
};

module.exports = {
    listCrawlLogs,
    getCrawlLogDetail,
    getDetailBySymbol,
    getFailedSymbols
};