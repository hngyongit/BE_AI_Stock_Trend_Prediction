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

const registerValidationRules = [
  body('full_name')
    .notEmpty().withMessage('Full name is required')
    .trim()
    .isLength({ min: 2, max: 100 }).withMessage('Full name must be between 2 and 100 characters'),
  body('email')
    .notEmpty().withMessage('Email is required')
    .isEmail().withMessage('Invalid email format')
    .normalizeEmail(),
  body('password')
    .notEmpty().withMessage('Password is required')
    .isLength({ min: 8 }).withMessage('Password must be at least 8 characters long')
];

const oauthExchangeValidationRules = [
  body('code')
    .notEmpty()
    .withMessage('Exchange code is required')
    .trim()
    .isLength({ min: 32, max: 64 })
    .withMessage('Invalid exchange code')
];

module.exports = {
  loginValidationRules,
  refreshTokenValidationRules,
  registerValidationRules,
  oauthExchangeValidationRules,
  validate
};
