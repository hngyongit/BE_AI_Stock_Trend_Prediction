const { body, query, validationResult } = require('express-validator');
const { error } = require('../../common/utils/response.util');

const updateProfileRules = [
  body('full_name')
    .optional()
    .trim()
    .isLength({ min: 2, max: 100 }).withMessage('Full name must be between 2 and 100 characters')
];

const changePasswordRules = [
  body('current_password')
    .notEmpty().withMessage('Current password is required'),
  body('new_password')
    .notEmpty().withMessage('New password is required')
    .isLength({ min: 8 }).withMessage('New password must be at least 8 characters long')
];

const updateRoleRules = [
  body('role')
    .notEmpty().withMessage('Role is required')
    .isIn(['USER', 'STAFF']).withMessage('Role must be USER or STAFF')
];

const queryUsersRules = [
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
    .isIn(['ACTIVE', 'LOCKED']).withMessage('Status must be ACTIVE or LOCKED'),
  query('role')
    .optional()
    .isIn(['USER', 'STAFF', 'ADMIN']).withMessage('Role must be USER, STAFF or ADMIN')
];

// Helper middleware to execute validations
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
  updateProfileRules,
  changePasswordRules,
  updateRoleRules,
  queryUsersRules,
  validate
};
