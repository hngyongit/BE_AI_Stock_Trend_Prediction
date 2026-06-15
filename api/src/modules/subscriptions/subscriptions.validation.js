const { body, validationResult } = require('express-validator');
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

const createPaymentValidation = [
    body('amount')
        .optional()
        .isInt({ min: 1000 }).withMessage('Amount must be at least 1000 VND')
];

module.exports = {
    validate,
    createPaymentValidation
};