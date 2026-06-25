const CrawlJob = require('../../database/models/crawl-job.model');

/**
 * Helper to calculate next_run_at from a cron expression.
 * For MVP, this is a placeholder that sets next_run_at 24 hours from now.
 * A real cron parser (e.g., node-cron, cron-parser) can be added later.
 */
const calculateNextRun = (cronExpression) => {
    const next = new Date();
    next.setHours(next.getHours() + 24);
    return next;
};

/**
 * Staff: Get paginated list of crawl jobs (filterable)
 */
const listCrawlJobs = async (queries) => {
    const page = parseInt(queries.page || '1', 10);
    const limit = parseInt(queries.limit || '20', 10);
    const skip = (page - 1) * limit;

    const filter = {};

    // Keyword search (job_name)
    if (queries.keyword) {
        filter.job_name = { $regex: queries.keyword, $options: 'i' };
    }

    // Status filter
    if (queries.status) {
        filter.status = queries.status;
    }

    // Data type filter
    if (queries.data_type) {
        filter.data_type = queries.data_type;
    }

    // Data source filter
    if (queries.data_source_id) {
        filter.data_source_id = queries.data_source_id;
    }

    // Market filter
    if (queries.market_id) {
        filter.market_id = queries.market_id;
    }

    // Sort
    const sortField = queries.sort_by || 'created_at';
    const sortOrder = queries.sort_order === 'asc' ? 1 : -1;

    const items = await CrawlJob.find(filter)
        .populate('data_source_id', 'name provider_type')
        .populate('market_id', 'code name')
        .sort({ [sortField]: sortOrder })
        .skip(skip)
        .limit(limit);

    const total_items = await CrawlJob.countDocuments(filter);
    const total_pages = Math.ceil(total_items / limit);

    return {
        items,
        pagination: { page, limit, total_items, total_pages }
    };
};

/**
 * Staff: Get a single crawl job by ID with recent logs
 */
const getCrawlJobDetail = async (id) => {
    const job = await CrawlJob.findById(id)
        .populate('data_source_id', 'name provider_type base_url')
        .populate('market_id', 'code name');

    if (!job) {
        const error = new Error('Crawl job not found');
        error.statusCode = 404;
        throw error;
    }

    return job;
};

/**
 * Staff: Create a new crawl job
 */
const createCrawlJob = async (data) => {
    const job = await CrawlJob.create({
        job_name: data.job_name,
        data_source_id: data.data_source_id,
        market_id: data.market_id,
        data_type: data.data_type,
        cron_expression: data.cron_expression,
        crawl_mode: data.crawl_mode || 'scheduled',
        status: data.status || 'active',
        next_run_at: calculateNextRun(data.cron_expression)
    });

    return job;
};

/**
 * Staff: Update an existing crawl job
 */
const updateCrawlJob = async (id, data) => {
    const job = await CrawlJob.findById(id);
    if (!job) {
        const error = new Error('Crawl job not found');
        error.statusCode = 404;
        throw error;
    }

    const updateFields = {};
    if (data.job_name !== undefined) updateFields.job_name = data.job_name;
    if (data.data_source_id !== undefined) updateFields.data_source_id = data.data_source_id;
    if (data.market_id !== undefined) updateFields.market_id = data.market_id;
    if (data.data_type !== undefined) updateFields.data_type = data.data_type;
    if (data.cron_expression !== undefined) {
        updateFields.cron_expression = data.cron_expression;
        updateFields.next_run_at = calculateNextRun(data.cron_expression);
    }
    if (data.crawl_mode !== undefined) updateFields.crawl_mode = data.crawl_mode;
    if (data.status !== undefined) updateFields.status = data.status;

    Object.assign(job, updateFields);
    await job.save();

    return job;
};

/**
 * Staff: Toggle crawl job status (active ↔ inactive)
 */
const toggleCrawlJobStatus = async (id) => {
    const job = await CrawlJob.findById(id);
    if (!job) {
        const error = new Error('Crawl job not found');
        error.statusCode = 404;
        throw error;
    }

    job.status = job.status === 'active' ? 'inactive' : 'active';
    if (job.status === 'active') {
        job.next_run_at = calculateNextRun(job.cron_expression);
    } else {
        job.next_run_at = null;
    }
    await job.save();

    return job;
};

module.exports = {
    listCrawlJobs,
    getCrawlJobDetail,
    createCrawlJob,
    updateCrawlJob,
    toggleCrawlJobStatus
};