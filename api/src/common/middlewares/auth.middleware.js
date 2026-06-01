const { verifyAccessToken } = require('../utils/jwt.util');
const User = require('../../database/models/user.model');
const { error } = require('../utils/response.util');

const authMiddleware = async (req, res, next) => {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return error(res, 'Unauthorized', null, 401);
    }

    const token = authHeader.split(' ')[1];
    const decoded = verifyAccessToken(token);
    if (!decoded) {
      return error(res, 'Unauthorized', null, 401);
    }

    const user = await User.findById(decoded.user_id).populate('role_id');
    if (!user) {
      return error(res, 'Unauthorized', null, 401);
    }

    if (user.status !== 'ACTIVE') {
      if (user.status === 'LOCKED') {
        return error(res, 'Account is locked', null, 403);
      }
      return error(res, `Account is status: ${user.status}`, null, 403);
    }

    req.user = user;
    next();
  } catch (err) {
    console.error(`[Auth Middleware] Error: ${err.message}`);
    return error(res, 'Internal server error during authentication', null, 500);
  }
};

module.exports = authMiddleware;
