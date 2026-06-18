const { body, query, validationResult } = require('express-validator');
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
  query('role')
    .optional()
    .isIn(['USER', 'STAFF', 'ADMIN']).withMessage('Role must be USER, STAFF or ADMIN'),
  query('sort_by')
    .optional()
    .isIn(['created_at', 'subscription_expires_at', 'plan']).withMessage('Invalid sort field'),
  query('sort_order')
    .optional()
    .isIn(['asc', 'desc']).withMessage('Sort order must be asc or desc')
];

const renewGrantValidation = [
  body('duration_days')
    .isInt({ min: 1, max: 365 })
    .withMessage('Duration days must be between 1 and 365'),
  body('notes')
    .optional()
    .isString().trim()
    .isLength({ max: 500 })
];

const cancelValidation = [
  body('notes')
    .optional()
    .isString().trim()
    .isLength({ max: 500 })
];

const modifyExpiryValidation = [
  body('expires_at')
    .isISO8601()
    .withMessage('Expires at must be a valid ISO 8601 date'),
  body('notes')
    .optional()
    .isString().trim()
    .isLength({ max: 500 })
];

module.exports = {
  validate,
  listSubscriptionsRules,
  renewGrantValidation,
  cancelValidation,
  modifyExpiryValidation
};
