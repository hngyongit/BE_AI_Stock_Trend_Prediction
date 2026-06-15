const dashboardService = require('./dashboard.service');
const { success } = require('../../common/utils/response.util');

/**
 * Controller for GET /api/dashboard/user
 */
const getUserDashboard = async (req, res, next) => {
  try {
    const userId = req.user._id || req.user.id;
    const result = await dashboardService.getUserDashboard(userId);
    return success(res, 'Get user dashboard successfully', result);
  } catch (error) {
    next(error);
  }
};

/**
 * Controller for GET /api/dashboard/staff
 */
const getStaffDashboard = async (req, res, next) => {
  try {
    const result = await dashboardService.getStaffDashboard();
    return success(res, 'Get staff dashboard successfully', result);
  } catch (error) {
    next(error);
  }
};

/**
 * Controller for GET /api/dashboard/admin
 */
const getAdminDashboard = async (req, res, next) => {
  try {
    const result = await dashboardService.getAdminDashboard();
    return success(res, 'Get admin dashboard successfully', result);
  } catch (error) {
    next(error);
  }
};

module.exports = {
  getUserDashboard,
  getStaffDashboard,
  getAdminDashboard
};
