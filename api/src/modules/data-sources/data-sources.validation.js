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

const createDataSourceRules = [
    body('name')
        .trim()
        .notEmpty().withMessage('Name is required')
        .isLength({ max: 100 }).withMessage('Name must be at most 100 characters'),
    body('provider_type')
        .optional()
        .isIn(['crawler', 'api', 'file_import']).withMessage('Provider type must be crawler, api, or file_import'),
    body('base_url')
        .optional()
        .trim(),
    body('description')
        .optional()
        .trim(),
    body('status')
        .optional()
        .isIn(['active', 'inactive']).withMessage('Status must be active or inactive')
];

const updateDataSourceRules = [
    param('id')
        .isMongoId().withMessage('Invalid data source ID'),
    body('name')
        .optional()
        .trim()
        .notEmpty().withMessage('Name cannot be empty')
        .isLength({ max: 100 }).withMessage('Name must be at most 100 characters'),
    body('provider_type')
        .optional()
        .isIn(['crawler', 'api', 'file_import']).withMessage('Provider type must be crawler, api, or file_import'),
    body('base_url')
        .optional()
        .trim(),
    body('description')
        .optional()
        .trim(),
    body('status')
        .optional()
        .isIn(['active', 'inactive']).withMessage('Status must be active or inactive')
];

const toggleStatusRules = [
    param('id')
        .isMongoId().withMessage('Invalid data source ID')
];

const listDataSourcesRules = [
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
    query('provider_type')
        .optional()
        .isIn(['crawler', 'api', 'file_import']).withMessage('Invalid provider type'),
    query('keyword')
        .optional()
        .trim(),
    query('sort_by')
        .optional()
        .isIn(['name', 'provider_type', 'status', 'created_at']).withMessage('Invalid sort field'),
    query('sort_order')
        .optional()
        .isIn(['asc', 'desc']).withMessage('Sort order must be asc or desc')
];

const getDataSourceRules = [
    param('id')
        .isMongoId().withMessage('Invalid data source ID')
];

module.exports = {
    validate,
    createDataSourceRules,
    updateDataSourceRules,
    toggleStatusRules,
    listDataSourcesRules,
    getDataSourceRules
};