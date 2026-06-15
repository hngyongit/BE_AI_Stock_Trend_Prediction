const jwt = require('jsonwebtoken');
const jwtConfig = require('../../config/jwt.config');

/**
 * Generate JWT access token for a user
 * @param {Object} user 
 * @returns {String} Token
 */
const generateAccessToken = (user) => {
  // role could be populated object or just plain string (or id)
  let roleName = 'USER';
  if (user.role_id && typeof user.role_id === 'object' && user.role_id.name) {
    roleName = user.role_id.name;
  } else if (user.role) {
    roleName = user.role;
  }

  const payload = {
    user_id: user._id || user.id,
    email: user.email,
    role: roleName,
    plan: user.plan || 'FREE'
  };

  return jwt.sign(payload, jwtConfig.accessSecret, {
    expiresIn: jwtConfig.accessExpiresIn
  });
};

/**
 * Generate JWT refresh token for a user
 * @param {Object} user 
 * @returns {String} Token
 */
const generateRefreshToken = (user) => {
  const payload = {
    user_id: user._id || user.id,
    token_type: 'refresh'
  };

  return jwt.sign(payload, jwtConfig.refreshSecret, {
    expiresIn: jwtConfig.refreshExpiresIn
  });
};

/**
 * Verify access token and return decoded payload or null
 * @param {String} token 
 * @returns {Object|null}
 */
const verifyAccessToken = (token) => {
  try {
    return jwt.verify(token, jwtConfig.accessSecret);
  } catch (error) {
    return null;
  }
};

/**
 * Verify refresh token and return decoded payload or null
 * @param {String} token 
 * @returns {Object|null}
 */
const verifyRefreshToken = (token) => {
  try {
    return jwt.verify(token, jwtConfig.refreshSecret);
  } catch (error) {
    return null;
  }
};

module.exports = {
  generateAccessToken,
  generateRefreshToken,
  verifyAccessToken,
  verifyRefreshToken
};
