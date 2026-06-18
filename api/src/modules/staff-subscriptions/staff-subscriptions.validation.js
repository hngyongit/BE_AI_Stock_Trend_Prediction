const { query, validationResult } = require('express-validator');
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

const listSubscriptionsRules = [
  query('page')
    .optional()
    .isInt({ min: 1 }).withMessage('Page must be a positive integer')
    .toInt(),
  query('limit')
    .optional()
    .isInt({ min: 1, max: 100 }).withMessage('Limit must be between 1 and 100')
    .toInt(),
  query('plan')
    .optional()
    .isIn(['FREE', 'PRO']).withMessage('Plan must be FREE or PRO'),
  query('status')
    .optional()
    .isIn(['NONE', 'ACTIVE', 'EXPIRED', 'CANCELLED']).withMessage('Invalid subscription status'),
  query('sort_by')
    .optional()
    .isIn(['created_at', 'subscription_expires_at', 'plan']).withMessage('Invalid sort field'),
  query('sort_order')
    .optional()
    .isIn(['asc', 'desc']).withMessage('Sort order must be asc or desc')
];

module.exports = {
  validate,
  listSubscriptionsRules
};
