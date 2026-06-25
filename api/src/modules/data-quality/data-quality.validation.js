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

const missingRecordsRules = [
    query('date_from')
        .optional()
        .isISO8601().withMessage('Invalid date_from format (use YYYY-MM-DD)'),
    query('date_to')
        .optional()
        .isISO8601().withMessage('Invalid date_to format (use YYYY-MM-DD)')
];

module.exports = {
    validate,
    missingRecordsRules
};