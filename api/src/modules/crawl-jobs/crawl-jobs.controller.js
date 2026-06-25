const crawlJobsService = require('./crawl-jobs.service');
const { success } = require('../../common/utils/response.util');

/**
 * Format crawl job object for API response
 */
const formatCrawlJob = (job) => ({
    id: job._id.toString(),
    job_name: job.job_name,
    data_source: job.data_source_id ? {
        id: job.data_source_id._id.toString(),
        name: job.data_source_id.name,
        provider_type: job.data_source_id.provider_type
    } : null,
    market: job.market_id ? {
        id: job.market_id._id.toString(),
        code: job.market_id.code,
        name: job.market_id.name
    } : null,
    data_type: job.data_type,
    cron_expression: job.cron_expression,
    crawl_mode: job.crawl_mode,
    status: job.status,
    last_run_at: job.last_run_at,
    next_run_at: job.next_run_at,
    created_at: job.created_at,
    updated_at: job.updated_at
});

/**
 * List crawl jobs (paginated, filterable)
 */
const list = async (req, res, next) => {
    try {
        const result = await crawlJobsService.listCrawlJobs(req.query);
        const formattedItems = result.items.map(formatCrawlJob);
        return success(res, 'Get crawl jobs successfully', {
            items: formattedItems,
            pagination: result.pagination
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Get a single crawl job by ID
 */
const detail = async (req, res, next) => {
    try {
        const { id } = req.params;
        const job = await crawlJobsService.getCrawlJobDetail(id);
        return success(res, 'Get crawl job successfully', {
            crawl_job: formatCrawlJob(job)
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Create a new crawl job
 */
const create = async (req, res, next) => {
    try {
        const job = await crawlJobsService.createCrawlJob(req.body);
        return success(res, 'Crawl job created successfully', {
            crawl_job: formatCrawlJob(job)
        }, 201);
    } catch (error) {
        next(error);
    }
};

/**
 * Update an existing crawl job
 */
const update = async (req, res, next) => {
    try {
        const { id } = req.params;
        const job = await crawlJobsService.updateCrawlJob(id, req.body);
        return success(res, 'Crawl job updated successfully', {
            crawl_job: formatCrawlJob(job)
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Toggle crawl job status (active ↔ inactive)
 */
const toggleStatus = async (req, res, next) => {
    try {
        const { id } = req.params;
        const job = await crawlJobsService.toggleCrawlJobStatus(id);
        return success(res, 'Crawl job status toggled successfully', {
            crawl_job: formatCrawlJob(job)
        });
    } catch (error) {
        next(error);
    }
};

module.exports = {
    list,
    detail,
    create,
    update,
    toggleStatus
};