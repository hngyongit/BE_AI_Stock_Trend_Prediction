const bcrypt = require('bcryptjs');
const User = require('../../database/models/user.model');
const Role = require('../../database/models/role.model');

/**
 * Get profile of current user
 * @param {String} userId 
 * @returns {Promise<Object>} user
 */
const getMe = async (userId) => {
  const user = await User.findById(userId).populate('role_id');
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }
  return user;
};

/**
 * Update personal profile information
 * @param {String} userId 
 * @param {String} fullName 
 * @returns {Promise<Object>} updated user
 */
const updateMe = async (userId, fullName) => {
  const user = await User.findById(userId).populate('role_id');
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  if (fullName) {
    user.full_name = fullName;
    await user.save();
  }

  return user;
};

/**
 * Change current user password
 * @param {String} userId 
 * @param {String} currentPassword 
 * @param {String} newPassword 
 */
const changePassword = async (userId, currentPassword, newPassword) => {
  const user = await User.findById(userId);
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  // Verify old password
  const isMatch = await user.comparePassword(currentPassword);
  if (!isMatch) {
    const error = new Error('Current password is incorrect');
    error.statusCode = 400;
    throw error;
  }

  // Prevent identical passwords
  if (currentPassword === newPassword) {
    const error = new Error('New password cannot be the same as the current password');
    error.statusCode = 400;
    throw error;
  }

  // Hash new password and invalidate active refresh sessions
  const salt = await bcrypt.genSalt(10);
  user.password_hash = await bcrypt.hash(newPassword, salt);
  user.refresh_token_hash = null;
  await user.save();

  return true;
};

/**
 * Admin: Retrieve paginated user listing with search filters
 * @param {Object} queries - query params { page, limit, keyword, role, status }
 */
const adminGetUsers = async (queries) => {
  const page = parseInt(queries.page || '1', 10);
  const limit = parseInt(queries.limit || '10', 10);
  const skip = (page - 1) * limit;

  const filter = {};

  if (queries.keyword) {
    const searchRegex = { $regex: queries.keyword, $options: 'i' };
    filter.$or = [
      { full_name: searchRegex },
      { email: searchRegex }
    ];
  }

  if (queries.status) {
    filter.status = queries.status;
  }

  if (queries.role) {
    const roleDoc = await Role.findOne({ name: queries.role.toUpperCase() });
    if (!roleDoc) {
      return {
        items: [],
        pagination: { page, limit, total_items: 0, total_pages: 0 }
      };
    }
    filter.role_id = roleDoc._id;
  }

  const items = await User.find(filter)
    .populate('role_id')
    .sort({ created_at: -1 })
    .skip(skip)
    .limit(limit);

  const total_items = await User.countDocuments(filter);
  const total_pages = Math.ceil(total_items / limit);

  return {
    items,
    pagination: {
      page,
      limit,
      total_items,
      total_pages
    }
  };
};

/**
 * Admin: Get user profile details
 * @param {String} userId 
 */
const adminGetUserById = async (userId) => {
  const user = await User.findById(userId).populate('role_id');
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }
  return user;
};

/**
 * Admin: Lock user account
 * @param {String} adminId 
 * @param {String} targetUserId 
 */
const adminLockUser = async (adminId, targetUserId) => {
  if (adminId.toString() === targetUserId.toString()) {
    const error = new Error('Admin cannot lock themselves or other admin accounts');
    error.statusCode = 400;
    throw error;
  }

  const user = await User.findById(targetUserId).populate('role_id');
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  // Prevent locking ADMINs
  if (user.role_id?.name === 'ADMIN') {
    const error = new Error('Admin cannot lock themselves or other admin accounts');
    error.statusCode = 400;
    throw error;
  }

  user.status = 'LOCKED';
  user.refresh_token_hash = null; // force terminate active sessions
  await user.save();

  return true;
};

/**
 * Admin: Unlock user account
 * @param {String} targetUserId 
 */
const adminUnlockUser = async (targetUserId) => {
  const user = await User.findById(targetUserId);
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  user.status = 'ACTIVE';
  await user.save();

  return true;
};

/**
 * Admin: Update user role
 * @param {String} targetUserId 
 * @param {String} newRoleName - USER or STAFF
 */
const adminUpdateUserRole = async (targetUserId, newRoleName) => {
  if (!['USER', 'STAFF'].includes(newRoleName.toUpperCase())) {
    const error = new Error('Role must be USER or STAFF');
    error.statusCode = 400;
    throw error;
  }

  const roleDoc = await Role.findOne({ name: newRoleName.toUpperCase() });
  if (!roleDoc) {
    const error = new Error('Role not found');
    error.statusCode = 404;
    throw error;
  }

  const user = await User.findById(targetUserId);
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  user.role_id = roleDoc._id;
  await user.save();

  const updatedUser = await User.findById(targetUserId).populate('role_id');
  return updatedUser;
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
