const { body, param, query, validationResult } = require('express-validator');
const { error } = require('../../common/utils/response.util');

const validate = (req, res, next) => {
    const errors = validationResult(req);
    if (errors.isEmpty()) {
        return next();
    }
    const extractedErrors = errors.array().map(err => ({
        field: err.path,
        message: err.msg
    }));
    return error(res, 'Validation failed', extractedErrors, 400);
};

const createCrawlJobRules = [
    body('job_name')
        .trim()
        .notEmpty().withMessage('Job name is required')
        .isLength({ max: 200 }).withMessage('Job name must be at most 200 characters'),
    body('data_source_id')
        .isMongoId().withMessage('Valid data source ID is required'),
    body('market_id')
        .isMongoId().withMessage('Valid market ID is required'),
    body('data_type')
        .isIn(['DAILY_MARKET_PRICE', 'QUARTERLY_FINANCIAL_STATEMENT', 'FINANCIAL_REPORT_SOURCE', 'MARKET_OVERVIEW'])
        .withMessage('Data type must be one of: DAILY_MARKET_PRICE, QUARTERLY_FINANCIAL_STATEMENT, FINANCIAL_REPORT_SOURCE, MARKET_OVERVIEW'),
    body('cron_expression')
        .trim()
        .notEmpty().withMessage('Cron expression is required'),
    body('crawl_mode')
        .optional()
        .isIn(['scheduled', 'manual']).withMessage('Crawl mode must be scheduled or manual'),
    body('status')
        .optional()
        .isIn(['active', 'inactive']).withMessage('Status must be active or inactive')
];

const updateCrawlJobRules = [
    param('id')
        .isMongoId().withMessage('Invalid crawl job ID'),
    body('job_name')
        .optional()
        .trim()
        .notEmpty().withMessage('Job name cannot be empty')
        .isLength({ max: 200 }).withMessage('Job name must be at most 200 characters'),
    body('data_source_id')
        .optional()
        .isMongoId().withMessage('Valid data source ID is required'),
    body('market_id')
        .optional()
        .isMongoId().withMessage('Valid market ID is required'),
    body('data_type')
        .optional()
        .isIn(['DAILY_MARKET_PRICE', 'QUARTERLY_FINANCIAL_STATEMENT', 'FINANCIAL_REPORT_SOURCE', 'MARKET_OVERVIEW'])
        .withMessage('Invalid data type'),
    body('cron_expression')
        .optional()
        .trim()
        .notEmpty().withMessage('Cron expression cannot be empty'),
    body('crawl_mode')
        .optional()
        .isIn(['scheduled', 'manual']).withMessage('Crawl mode must be scheduled or manual'),
    body('status')
        .optional()
        .isIn(['active', 'inactive']).withMessage('Status must be active or inactive')
];

const toggleStatusRules = [
    param('id')
        .isMongoId().withMessage('Invalid crawl job ID')
];

const listCrawlJobsRules = [
    query('page')
        .optional()
        .isInt({ min: 1 }).withMessage('Page must be a positive integer')
        .toInt(),
    query('limit')
        .optional()
        .isInt({ min: 1, max: 100 }).withMessage('Limit must be between 1 and 100')
        .toInt(),
    query('status')
        .optional()
        .isIn(['active', 'inactive']).withMessage('Status must be active or inactive'),
    query('data_type')
        .optional()
        .isIn(['DAILY_MARKET_PRICE', 'QUARTERLY_FINANCIAL_STATEMENT', 'FINANCIAL_REPORT_SOURCE', 'MARKET_OVERVIEW'])
        .withMessage('Invalid data type'),
    query('data_source_id')
        .optional()
        .isMongoId().withMessage('Invalid data source ID'),
    query('market_id')
        .optional()
        .isMongoId().withMessage('Invalid market ID'),
    query('keyword')
        .optional()
        .trim(),
    query('sort_by')
        .optional()
        .isIn(['job_name', 'data_type', 'status', 'created_at', 'next_run_at']).withMessage('Invalid sort field'),
    query('sort_order')
        .optional()
        .isIn(['asc', 'desc']).withMessage('Sort order must be asc or desc')
];

const getCrawlJobRules = [
    param('id')
        .isMongoId().withMessage('Invalid crawl job ID')
];

module.exports = {
    validate,
    createCrawlJobRules,
    updateCrawlJobRules,
    toggleStatusRules,
    listCrawlJobsRules,
    getCrawlJobRules
};