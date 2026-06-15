const { body, param, validationResult } = require('express-validator');
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

const addWatchlistValidation = [
  body('symbol')
    .notEmpty().withMessage('Symbol is required')
    .trim()
    .toUpperCase()
    .isLength({ min: 3, max: 10 }).withMessage('Symbol must be between 3 and 10 characters')
];

const removeWatchlistValidation = [
  param('symbol')
    .notEmpty().withMessage('Symbol is required')
    .trim()
    .toUpperCase()
];

const trimWatchlistValidation = [
  body('keepStockIds')
    .isArray({ min: 1 }).withMessage('keepStockIds must be a non-empty array')
    .custom((ids) => ids.every(id => typeof id === 'string' && id.length > 0))
    .withMessage('Each keepStockId must be a non-empty string')
];

module.exports = {
  validate,
  addWatchlistValidation,
  removeWatchlistValidation,
  trimWatchlistValidation
};
