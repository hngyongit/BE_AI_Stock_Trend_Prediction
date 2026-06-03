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
 * Register Controller
 */
const register = async (req, res, next) => {
  try {
    const { full_name, email, password } = req.body;
    const user = await authService.register(full_name, email, password);

    // Format output to match standard response
    const formattedUser = {
      id: user._id.toString(),
      full_name: user.full_name,
      email: user.email,
      role: user.role_id?.name || 'USER',
      status: user.status
    };

    return success(res, 'User registered successfully', {
      user: formattedUser
    }, 201);
  } catch (error) {
    next(error);
  }
};

module.exports = {
  login,
  logout,
  refreshToken,
  register
};
