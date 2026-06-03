const { query, param, body, validationResult } = require('express-validator');
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

const getStocksValidation = [
  query('page').optional().isInt({ min: 1 }).withMessage('Page must be a positive integer'),
  query('limit').optional().isInt({ min: 1 }).withMessage('Limit must be a positive integer'),
  query('keyword').optional().trim(),
  query('market').optional().trim().toUpperCase()
];

const getChartValidation = [
  param('symbol').notEmpty().withMessage('Symbol is required').trim().toUpperCase(),
  query('range').optional().toLowerCase().isIn(['7d', '1m', '3m', '6m', '1y', 'all']).withMessage('Range must be one of: 7d, 1m, 3m, 6m, 1y, all')
];

const createStockValidation = [
  body('symbol')
    .notEmpty().withMessage('Symbol is required')
    .trim()
    .toUpperCase()
    .isLength({ min: 3, max: 10 }).withMessage('Symbol must be between 3 and 10 characters'),
  body('company_name')
    .notEmpty().withMessage('Company name is required')
    .trim()
    .isLength({ min: 2 }).withMessage('Company name must be at least 2 characters'),
  body('exchange_code')
    .notEmpty().withMessage('Exchange code is required')
    .trim()
    .toUpperCase(),
  body('status')
    .optional()
    .isIn(['ACTIVE', 'DELISTED', 'SUSPENDED']).withMessage('Status must be ACTIVE, DELISTED, or SUSPENDED'),
  body('listed_date')
    .optional()
    .isISO8601().withMessage('Listed date must be a valid ISO8601 date')
];

const updateStockValidation = [
  param('id').isMongoId().withMessage('Invalid stock ID format'),
  body('company_name')
    .optional()
    .trim()
    .isLength({ min: 2 }).withMessage('Company name must be at least 2 characters'),
  body('exchange_code')
    .optional()
    .trim()
    .toUpperCase(),
  body('status')
    .optional()
    .isIn(['ACTIVE', 'DELISTED', 'SUSPENDED']).withMessage('Status must be ACTIVE, DELISTED, or SUSPENDED'),
  body('listed_date')
    .optional()
    .isISO8601().withMessage('Listed date must be a valid ISO8601 date')
];

module.exports = {
  validate,
  getStocksValidation,
  getChartValidation,
  createStockValidation,
  updateStockValidation
};
