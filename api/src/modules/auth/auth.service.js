const bcrypt = require('bcryptjs');
const User = require('../../database/models/user.model');
const Role = require('../../database/models/role.model');
const { generateAccessToken, generateRefreshToken, verifyRefreshToken } = require('../../common/utils/jwt.util');
const oauthExchangeStore = require('../../common/stores/oauth-exchange.store');

/**
 * Issue access + refresh tokens, persist refresh hash (same contract as password login).
 * @param {object} user - Mongoose user document with populated role_id
 * @returns {Promise<{ access_token: string, refresh_token: string, user: object }>}
 */
const issueTokensForUser = async (user) => {
  if (!user) {
    const err = new Error('User not found');
    err.statusCode = 401;
    throw err;
  }

  if (user.status !== 'ACTIVE') {
    if (user.status === 'LOCKED') {
      const err = new Error('Account is locked');
      err.statusCode = 403;
      throw err;
    }
    const err = new Error(`Account is ${String(user.status).toLowerCase()}`);
    err.statusCode = 403;
    throw err;
  }

  const accessToken = generateAccessToken(user);
  const refreshToken = generateRefreshToken(user);

  const salt = await bcrypt.genSalt(10);
  const hashedRefreshToken = await bcrypt.hash(refreshToken, salt);
  user.refresh_token_hash = hashedRefreshToken;
  user.last_login_at = new Date();
  await user.save();

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
 * Find or create user from Google profile. Links google_id to existing email account when Google email is verified (MVP policy).
 * @param {object} profile - passport-google-oauth20 profile
 * @param {{ signupOnly?: boolean }} [options] - If signupOnly, reject when email already exists (unless this Google id already owns the account).
 */
const findOrCreateOrLinkGoogleUser = async (profile, options = {}) => {
  const { signupOnly = false } = options;
  const googleId = profile.id;
  const displayName = profile.displayName || 'Google User';
  const primaryEmail = profile.emails?.[0]?.value?.toLowerCase().trim();
  const emailRow = profile.emails?.[0];
  const emailVerified =
    emailRow?.verified === true || profile._json?.email_verified === true;

  if (!primaryEmail) {
    const err = new Error('Google account has no email');
    err.statusCode = 400;
    throw err;
  }

  let user = await User.findOne({ google_id: googleId }).populate('role_id');
  if (user) {
    if (user.status !== 'ACTIVE') {
      if (user.status === 'LOCKED') {
        const err = new Error('Account is locked');
        err.statusCode = 403;
        throw err;
      }
      const err = new Error(`Account is ${String(user.status).toLowerCase()}`);
      err.statusCode = 403;
      throw err;
    }
    return user;
  }

  const byEmail = await User.findOne({ email: primaryEmail }).populate('role_id');
  if (byEmail) {
    if (signupOnly) {
      if (byEmail.google_id && byEmail.google_id === googleId) {
        if (byEmail.status !== 'ACTIVE') {
          if (byEmail.status === 'LOCKED') {
            const err = new Error('Account is locked');
            err.statusCode = 403;
            throw err;
          }
          const err = new Error(`Account is ${String(byEmail.status).toLowerCase()}`);
          err.statusCode = 403;
          throw err;
        }
        return byEmail;
      }
      const err = new Error(
        'Email is already registered. Sign in with Google or email instead.'
      );
      err.statusCode = 409;
      throw err;
    }

    if (byEmail.status !== 'ACTIVE') {
      if (byEmail.status === 'LOCKED') {
        const err = new Error('Account is locked');
        err.statusCode = 403;
        throw err;
      }
      const err = new Error(`Account is ${String(byEmail.status).toLowerCase()}`);
      err.statusCode = 403;
      throw err;
    }
    if (!emailVerified) {
      const err = new Error('Google email is not verified; cannot link to existing account');
      err.statusCode = 403;
      throw err;
    }
    byEmail.google_id = googleId;
    await byEmail.save();
    return User.findById(byEmail._id).populate('role_id');
  }

  const userRole = await Role.findOne({ name: 'USER' });
  if (!userRole) {
    const err = new Error('Standard USER role not found in system');
    err.statusCode = 500;
    throw err;
  }

  const created = await User.create({
    full_name: displayName,
    email: primaryEmail,
    password_hash: null,
    google_id: googleId,
    role_id: userRole._id,
    status: 'ACTIVE'
  });

  return User.findById(created._id).populate('role_id');
};

/**
 * One-time code for frontend POST /oauth/exchange (avoids putting refresh_token in browser history).
 * @param {object} user - Mongoose user document
 * @returns {Promise<string>}
 */
const createGoogleOAuthExchangeCode = async (user) => {
  const result = await issueTokensForUser(user);
  const formattedUser = {
    id: result.user._id ? result.user._id.toString() : result.user.id,
    full_name: result.user.full_name,
    email: result.user.email,
    role: result.user.role,
    status: result.user.status
  };
  return oauthExchangeStore.put({
    access_token: result.access_token,
    refresh_token: result.refresh_token,
    user: formattedUser
  });
};

const exchangeOAuthCode = (code) => {
  const data = oauthExchangeStore.take(code);
  if (!data) {
    const err = new Error('Invalid or expired exchange code');
    err.statusCode = 400;
    throw err;
  }
  return data;
};

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

  if (user.status !== 'ACTIVE') {
    if (user.status === 'LOCKED') {
      const err = new Error('Account is locked');
      err.statusCode = 403;
      throw err;
    }
    const err = new Error(`Account is ${String(user.status).toLowerCase()}`);
    err.statusCode = 403;
    throw err;
  }

  const isMatch = await user.comparePassword(password);
  if (!isMatch) {
    const error = new Error('Invalid email or password');
    error.statusCode = 401;
    throw error;
  }

  return issueTokensForUser(user);
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

  const existingUser = await User.findOne({ email: normalizedEmail });
  if (existingUser) {
    const error = new Error('Email is already registered');
    error.statusCode = 400;
    throw error;
  }

  const userRole = await Role.findOne({ name: 'USER' });
  if (!userRole) {
    const error = new Error('Standard USER role not found in system');
    error.statusCode = 500;
    throw error;
  }

  const salt = await bcrypt.genSalt(10);
  const hashedPassword = await bcrypt.hash(password, salt);

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
  register,
  issueTokensForUser,
  findOrCreateOrLinkGoogleUser,
  createGoogleOAuthExchangeCode,
  exchangeOAuthCode
};
