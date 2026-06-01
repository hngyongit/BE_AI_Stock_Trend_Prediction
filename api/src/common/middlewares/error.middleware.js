const { error } = require('../utils/response.util');

/**
 * Global unhandled error handling middleware
 */
const errorMiddleware = (err, req, res, next) => {
  console.error('[Unhandled Error]', err);

  const statusCode = err.statusCode || 500;
  const message = err.message || 'Internal Server Error';

  // Include stack details in development mode
  const errors = process.env.NODE_ENV === 'development' ? err.stack : null;

  return error(res, message, errors, statusCode);
};

module.exports = errorMiddleware;
