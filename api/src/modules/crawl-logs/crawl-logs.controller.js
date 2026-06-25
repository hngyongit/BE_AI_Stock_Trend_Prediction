const crawlLogsService = require('./crawl-logs.service');
const { success } = require('../../common/utils/response.util');

/**
 * Format crawl log for API response
 */
const formatCrawlLog = (log) => ({
    id: log._id.toString(),
    crawl_job: log.crawl_job_id ? {
        id: log.crawl_job_id._id.toString(),
        job_name: log.crawl_job_id.job_name,
        data_type: log.crawl_job_id.data_type
    } : null,
    started_at: log.started_at,
    ended_at: log.ended_at,
    status: log.status,
    records_fetched: log.records_fetched,
    records_inserted: log.records_inserted,
    records_updated: log.records_updated,
    records_failed: log.records_failed,
    error_message: log.error_message,
    created_at: log.created_at
});

/**
 * Format crawl log detail for API response
 */
const formatDetail = (detail) => ({
    id: detail._id.toString(),
    stock: detail.stock_id ? {
        id: detail.stock_id._id.toString(),
        symbol: detail.stock_id.symbol,
        company_name: detail.stock_id.company_name
    } : null,
    symbol: detail.symbol,
    data_type: detail.data_type,
    status: detail.status,
    message: detail.message,
    created_at: detail.created_at
});

/**
 * List crawl logs (paginated, filterable)
 */
const list = async (req, res, next) => {
    try {
        const result = await crawlLogsService.listCrawlLogs(req.query);
        const formattedItems = result.items.map(formatCrawlLog);
        return success(res, 'Get crawl logs successfully', {
            items: formattedItems,
            pagination: result.pagination
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Get a single crawl log with all its detail records
 */
const detail = async (req, res, next) => {
    try {
        const { id } = req.params;
        const { log, details } = await crawlLogsService.getCrawlLogDetail(id);
        return success(res, 'Get crawl log successfully', {
            crawl_log: formatCrawlLog(log),
            details: details.map(formatDetail)
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Get details by symbol within a crawl log
 */
const detailBySymbol = async (req, res, next) => {
    try {
        const { id } = req.params;
        const { symbol } = req.query;
        if (!symbol) {
            return success(res, 'Get crawl log details', {
                crawl_log: null,
                details: []
            });
        }
        const { log, details } = await crawlLogsService.getDetailBySymbol(id, symbol);
        return success(res, 'Get crawl log details by symbol successfully', {
            crawl_log: formatCrawlLog(log),
            details: details.map(formatDetail)
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Get all FAILED details across logs
 */
const failedSymbols = async (req, res, next) => {
    try {
        const { id } = req.params;
        const result = await crawlLogsService.getFailedSymbols({ ...req.query, crawl_log_id: id });
        return success(res, 'Get failed symbols successfully', {
            items: result.items.map(formatDetail),
            total: result.total
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Get all FAILED details across all logs (optionally filtered by job)
 */
const allFailedSymbols = async (req, res, next) => {
    try {
        const result = await crawlLogsService.getFailedSymbols(req.query);
        return success(res, 'Get all failed symbols successfully', {
            items: result.items.map(formatDetail),
            total: result.total
        });
    } catch (error) {
        next(error);
    }
};

module.exports = {
    list,
    detail,
    detailBySymbol,
    failedSymbols,
    allFailedSymbols
};