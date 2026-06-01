const { body, validationResult } = require('express-validator');
const { error } = require('../../common/utils/response.util');

const loginValidationRules = [
  body('email')
    .notEmpty().withMessage('Email is required')
    .isEmail().withMessage('Invalid email format')
    .normalizeEmail(),
  body('password')
    .notEmpty().withMessage('Password is required')
    .isLength({ min: 8 }).withMessage('Password must be at least 8 characters long')
];

const refreshTokenValidationRules = [
  body('refresh_token')
    .notEmpty().withMessage('Refresh token is required')
];

// Helper middleware to execute validation checks
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

module.exports = {
  loginValidationRules,
  refreshTokenValidationRules,
  validate
};
