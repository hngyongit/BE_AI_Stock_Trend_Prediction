const usersService = require('./users.service');
const { success } = require('../../common/utils/response.util');

/**
 * Format DB User entity for client responses
 */
const formatUser = (user, includeTimestamps = false) => {
  const roleName = user.role_id?.name || 'USER';
  const formatted = {
    id: user._id.toString(),
    full_name: user.full_name,
    email: user.email,
    role: roleName,
    status: user.status
  };

  if (includeTimestamps) {
    formatted.created_at = user.created_at;
    if (user.updated_at) {
      formatted.updated_at = user.updated_at;
    }
  }

  return formatted;
};

/**
 * Get profile of current user
 */
const getMe = async (req, res, next) => {
  try {
    const user = await usersService.getMe(req.user._id);
    return success(res, 'Get profile successfully', formatUser(user, true));
  } catch (error) {
    next(error);
  }
};

/**
 * Update personal profile information
 */
const updateMe = async (req, res, next) => {
  try {
    const { full_name } = req.body;
    const user = await usersService.updateMe(req.user._id, full_name);
    return success(res, 'Update profile successfully', formatUser(user, false));
  } catch (error) {
    next(error);
  }
};

/**
 * Change current user password
 */
const changePassword = async (req, res, next) => {
  try {
    const { current_password, new_password } = req.body;
    await usersService.changePassword(req.user._id, current_password, new_password);
    return success(res, 'Change password successfully');
  } catch (error) {
    next(error);
  }
};

/**
 * Admin: Retrieve paginated user listing
 */
const adminGetUsers = async (req, res, next) => {
  try {
    const result = await usersService.adminGetUsers(req.query);
    const formattedItems = result.items.map(user => formatUser(user, true));

    return success(res, 'Get users successfully', {
      items: formattedItems,
      pagination: result.pagination
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Admin: Get user profile details
 */
const adminGetUserById = async (req, res, next) => {
  try {
    const user = await usersService.adminGetUserById(req.params.id);
    return success(res, 'Get user detail successfully', formatUser(user, true));
  } catch (error) {
    next(error);
  }
};

/**
 * Admin: Lock user account
 */
const adminLockUser = async (req, res, next) => {
  try {
    await usersService.adminLockUser(req.user._id, req.params.id);
    return success(res, 'Lock user successfully');
  } catch (error) {
    next(error);
  }
};

/**
 * Admin: Unlock user account
 */
const adminUnlockUser = async (req, res, next) => {
  try {
    await usersService.adminUnlockUser(req.params.id);
    return success(res, 'Unlock user successfully');
  } catch (error) {
    next(error);
  }
};

/**
 * Admin: Update user role
 */
const adminUpdateUserRole = async (req, res, next) => {
  try {
    const { role } = req.body;
    const user = await usersService.adminUpdateUserRole(req.params.id, role);
    return success(res, 'Update user role successfully', formatUser(user, false));
  } catch (error) {
    next(error);
  }
};

module.exports = {
  getMe,
  updateMe,
  changePassword,
  adminGetUsers,
  adminGetUserById,
  adminLockUser,
  adminUnlockUser,
  adminUpdateUserRole
};
