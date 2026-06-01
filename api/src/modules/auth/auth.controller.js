const authService = require('./auth.service');
const { success } = require('../../common/utils/response.util');

/**
 * Login Controller
 */
const login = async (req, res, next) => {
  try {
    const { email, password } = req.body;
    const result = await authService.login(email, password);

    // Format output to match exact requirements
    const formattedUser = {
      id: result.user._id ? result.user._id.toString() : result.user.id,
      full_name: result.user.full_name,
      email: result.user.email,
      role: result.user.role,
      status: result.user.status
    };

    return success(res, 'Login successfully', {
      access_token: result.access_token,
      refresh_token: result.refresh_token,
      user: formattedUser
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Logout Controller
 */
const logout = async (req, res, next) => {
  try {
    const userId = req.user._id || req.user.id;
    await authService.logout(userId);
    return success(res, 'Logout successfully');
  } catch (error) {
    next(error);
  }
};

/**
 * Refresh Token Controller
 */
const refreshToken = async (req, res, next) => {
  try {
    const { refresh_token } = req.body;
    const result = await authService.refreshToken(refresh_token);
    return success(res, 'Refresh token successfully', result);
  } catch (error) {
    next(error);
  }
};

/**
 * Get Current User Profile Controller
 */
const getMe = async (req, res, next) => {
  try {
    const userObj = req.user.toJSON();
    const roleName = req.user.role_id?.name || 'USER';

    const formattedUser = {
      id: req.user._id.toString(),
      full_name: req.user.full_name,
      email: req.user.email,
      role: roleName,
      status: req.user.status,
      created_at: req.user.created_at
    };

    // Return the response format from Section 8.3
    // Note that Section 8.3 returns the user directly in "data" (e.g. data: { id, full_name... })
    // and success is helper wrapper which returns { success: true, data: formattedUser }
    return success(res, undefined, formattedUser);
  } catch (error) {
    next(error);
  }
};

module.exports = {
  login,
  logout,
  refreshToken,
  getMe
};
