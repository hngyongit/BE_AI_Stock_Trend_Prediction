const express = require('express');
const router = express.Router();

const dashboardController = require('./dashboard.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const roleMiddleware = require('../../common/middlewares/role.middleware');

/**
 * @openapi
 * tags:
 *   - name: Dashboard
 *     description: Role-specific metrics dashboards
 */

/**
 * @openapi
 * /api/dashboard/user:
 *   get:
 *     summary: Retrieve user dashboard
 *     description: Retrieve watchlist status and trends, alongside general market leaders. Restricted to users with USER role.
 *     tags: [Dashboard]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: User dashboard retrieved successfully.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Get user dashboard successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     watchlist:
 *                       type: object
 *                       properties:
 *                         total_stocks:
 *                           type: integer
 *                           example: 2
 *                         items:
 *                           type: array
 *                           items:
 *                             type: object
 *                         trends:
 *                           type: object
 *                           properties:
 *                             gainers:
 *                               type: integer
 *                               example: 1
 *                             losers:
 *                               type: integer
 *                               example: 1
 *                             flat:
 *                               type: integer
 *                               example: 0
 *                     market_leaders:
 *                       type: object
 *                       properties:
 *                         latest_trading_date:
 *                           type: integer
 *                           example: 20260612
 *                         gainers:
 *                           type: array
 *                           items:
 *                             type: object
 *                         losers:
 *                           type: array
 *                           items:
 *                             type: object
 *                     market_overview:
 *                       type: array
 *                       items:
 *                         type: object
 *                         properties:
 *                           symbol:
 *                             type: string
 *                             example: VNINDEX
 *                           display_symbol:
 *                             type: string
 *                             example: VNINDEX
 *                           market:
 *                             type: string
 *                             example: HOSE
 *                           close_index:
 *                             type: number
 *                             example: 1798.61
 *                           open_index:
 *                             type: number
 *                             example: 1813.07
 *                           high_index:
 *                             type: number
 *                             example: 1813.57
 *                           low_index:
 *                             type: number
 *                             example: 1788.8
 *                           change_value:
 *                             type: number
 *                             example: -6.96
 *                           change_percent:
 *                             type: number
 *                             example: -0.39
 *                           total_volume:
 *                             type: integer
 *                             example: 640199320
 *                           trading_date:
 *                             type: string
 *                             example: "2026-06-12"
 *                           chart:
 *                             type: array
 *                             items:
 *                               type: object
 *                               properties:
 *                                 date:
 *                                   type: string
 *                                   example: "2026-05-04"
 *                                 close:
 *                                   type: number
 *                                   example: 1874.85
 *                                 open:
 *                                   type: number
 *                                   example: 1853.08
 *                                 high:
 *                                   type: number
 *                                   example: 1875.97
 *                                 low:
 *                                   type: number
 *                                   example: 1849.32
 *                                 volume:
 *                                   type: integer
 *                                   example: 773453598
 *       401:
 *         description: Unauthorized. Missing or invalid Bearer access token.
 *       403:
 *         description: Forbidden. Insufficient permission.
 */
router.get('/user', authMiddleware, roleMiddleware(['USER']), dashboardController.getUserDashboard);

/**
 * @openapi
 * /api/dashboard/staff:
 *   get:
 *     summary: Retrieve staff dashboard
 *     description: Retrieve crawl jobs, log execution metadata, activity metrics, and general system catalog totals. Restricted to STAFF role.
 *     tags: [Dashboard]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Staff dashboard retrieved successfully.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Get staff dashboard successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     jobs:
 *                       type: object
 *                       properties:
 *                         total:
 *                           type: integer
 *                           example: 4
 *                         active:
 *                           type: integer
 *                           example: 3
 *                         inactive:
 *                           type: integer
 *                           example: 1
 *                     logs:
 *                       type: object
 *                       properties:
 *                         total_runs:
 *                           type: integer
 *                           example: 52
 *                         success_rate_percent:
 *                           type: number
 *                           example: 96.15
 *                         records_fetched:
 *                           type: integer
 *                           example: 1200
 *                         records_inserted:
 *                           type: integer
 *                           example: 200
 *                         records_updated:
 *                           type: integer
 *                           example: 1000
 *                         records_failed:
 *                           type: integer
 *                           example: 0
 *                     catalog:
 *                       type: object
 *                       properties:
 *                         total_stocks:
 *                           type: integer
 *                           example: 450
 *                         total_markets:
 *                           type: integer
 *                           example: 3
 *                         total_data_sources:
 *                           type: integer
 *                           example: 2
 *                     recent_activities:
 *                       type: array
 *                       items:
 *                         type: object
 *       401:
 *         description: Unauthorized. Missing or invalid Bearer access token.
 *       403:
 *         description: Forbidden. Insufficient permission.
 */
router.get('/staff', authMiddleware, roleMiddleware(['STAFF']), dashboardController.getStaffDashboard);

/**
 * @openapi
 * /api/dashboard/admin:
 *   get:
 *     summary: Retrieve admin dashboard
 *     description: Retrieve systems user registration metrics, role lists, watchlist metrics, and cron job reliability metrics. Restricted to ADMIN role.
 *     tags: [Dashboard]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Admin dashboard retrieved successfully.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Get admin dashboard successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     users:
 *                       type: object
 *                       properties:
 *                         total:
 *                           type: integer
 *                           example: 120
 *                         active:
 *                           type: integer
 *                           example: 118
 *                         locked:
 *                           type: integer
 *                           example: 2
 *                         new_registrations_last_7_days:
 *                           type: integer
 *                           example: 12
 *                         by_role:
 *                           type: object
 *                     watchlists:
 *                       type: object
 *                       properties:
 *                         total_entries:
 *                           type: integer
 *                           example: 80
 *                         active_users_count:
 *                           type: integer
 *                           example: 30
 *                         average_per_user:
 *                           type: number
 *                           example: 2.67
 *                     catalog:
 *                       type: object
 *                       properties:
 *                         total_stocks:
 *                           type: integer
 *                           example: 450
 *                         total_markets:
 *                           type: integer
 *                           example: 3
 *                     system_health:
 *                       type: object
 *                       properties:
 *                         crawl_success_rate_percent:
 *                           type: number
 *                           example: 96.15
 *                         total_crawl_runs:
 *                           type: integer
 *                           example: 52
 *       401:
 *         description: Unauthorized. Missing or invalid Bearer access token.
 *       403:
 *         description: Forbidden. Insufficient permission.
 */
router.get('/admin', authMiddleware, roleMiddleware(['ADMIN']), dashboardController.getAdminDashboard);

module.exports = {
  dashboardRouter: router
};
