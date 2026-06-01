const { error } = require('../utils/response.util');

/**
 * Role-based access control middleware
 * @param {String[]} allowedRoles - List of allowed role names, e.g. ['ADMIN', 'STAFF']
 */
const roleMiddleware = (allowedRoles = []) => {
  return (req, res, next) => {
    if (!req.user || !req.user.role_id) {
      return error(res, 'Forbidden', null, 403);
    }

    const userRole = req.user.role_id.name;
    if (!allowedRoles.includes(userRole)) {
      return error(res, 'Forbidden', null, 403);
    }

    next();
  };
};

module.exports = roleMiddleware;
