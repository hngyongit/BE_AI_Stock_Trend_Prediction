const bcrypt = require('bcryptjs');
const User = require('../../database/models/user.model');
const Role = require('../../database/models/role.model');
const { generateAccessToken, generateRefreshToken, verifyRefreshToken } = require('../../common/utils/jwt.util');

/**
 * Handle login logic
 * @param {String} email 
 * @param {String} password 
 * @returns {Promise<Object>} { access_token, refresh_token, user }
 */
const login = async (email, password) => {
  const user = await User.findOne({ email: email.toLowerCase() }).populate('role_id');
  if (!user) {
    const error = new Error('Invalid email or password');
    error.statusCode = 401;
    throw error;
  }

  // Check user account status
  if (user.status !== 'ACTIVE') {
    if (user.status === 'LOCKED') {
      const error = new Error('Account is locked');
      error.statusCode = 403;
      throw error;
    }
    const error = new Error(`Account is ${user.status.toLowerCase()}`);
    error.statusCode = 403;
    throw error;
  }

  // Validate password
  const isMatch = await user.comparePassword(password);
  if (!isMatch) {
    const error = new Error('Invalid email or password');
    error.statusCode = 401;
    throw error;
  }

  // Generate tokens
  const accessToken = generateAccessToken(user);
  const refreshToken = generateRefreshToken(user);

  // Hash and store refresh token
  const salt = await bcrypt.genSalt(10);
  const hashedRefreshToken = await bcrypt.hash(refreshToken, salt);
  user.refresh_token_hash = hashedRefreshToken;
  user.last_login_at = new Date();
  await user.save();

  // Construct client user representation
  const userObj = user.toJSON();
  userObj.role = user.role_id?.name || 'USER';
  delete userObj.role_id;

  return {
    access_token: accessToken,
    refresh_token: refreshToken,
    user: userObj
  };
};

/**
 * Handle logout logic
 * @param {String} userId 
 */
const logout = async (userId) => {
  const user = await User.findById(userId);
  if (user) {
    user.refresh_token_hash = null;
    await user.save();
  }
  return true;
};

/**
 * Reissue access token using a refresh token
 * @param {String} token - Refresh Token
 * @returns {Promise<Object>} { access_token }
 */
const refreshToken = async (token) => {
  const decoded = verifyRefreshToken(token);
  if (!decoded) {
    const error = new Error('Invalid refresh token');
    error.statusCode = 401;
    throw error;
  }

  const user = await User.findById(decoded.user_id).populate('role_id');
  if (!user || !user.refresh_token_hash) {
    const error = new Error('Invalid refresh token');
    error.statusCode = 401;
    throw error;
  }

  if (user.status !== 'ACTIVE') {
    const error = new Error('Account is not active');
    error.statusCode = 403;
    throw error;
  }

  // Compare candidate token with hashed token in database
  const isMatch = await bcrypt.compare(token, user.refresh_token_hash);
  if (!isMatch) {
    const error = new Error('Invalid refresh token');
    error.statusCode = 401;
    throw error;
  }

  const accessToken = generateAccessToken(user);
  return {
    access_token: accessToken
  };
};

/**
 * Register a new user
 * @param {String} fullName 
 * @param {String} email 
 * @param {String} password 
 * @returns {Promise<Object>} Created User
 */
const register = async (fullName, email, password) => {
  const normalizedEmail = email.toLowerCase();

  // Check if email already registered
  const existingUser = await User.findOne({ email: normalizedEmail });
  if (existingUser) {
    const error = new Error('Email is already registered');
    error.statusCode = 400;
    throw error;
  }

  // Find standard USER role
  const userRole = await Role.findOne({ name: 'USER' });
  if (!userRole) {
    const error = new Error('Standard USER role not found in system');
    error.statusCode = 500;
    throw error;
  }

  // Hash password
  const salt = await bcrypt.genSalt(10);
  const hashedPassword = await bcrypt.hash(password, salt);

  // Create User
  const newUser = await User.create({
    full_name: fullName,
    email: normalizedEmail,
    password_hash: hashedPassword,
    role_id: userRole._id,
    status: 'ACTIVE'
  });

  const userDoc = await User.findById(newUser._id).populate('role_id');
  return userDoc;
};

module.exports = {
  login,
  logout,
  refreshToken,
  register
};
