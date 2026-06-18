const express = require('express');
const router = express.Router();

const staffSubscriptionsController = require('./staff-subscriptions.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const roleMiddleware = require('../../common/middlewares/role.middleware');
const {
  validate,
  listSubscriptionsRules
} = require('./staff-subscriptions.validation');

// All routes require authentication + STAFF or ADMIN role
router.use(authMiddleware);
router.use(roleMiddleware(['ADMIN', 'STAFF']));

/**
 * @openapi
 * tags:
 *   - name: Staff Subscriptions
 *     description: STAFF read-only subscription access
 */

/**
 * @openapi
 * /api/staff/subscriptions:
 *   get:
 *     summary: List subscriptions (read-only)
 *     description: Returns paginated list of users with subscription info. STAFF only, no summary stats.
 *     tags: [Staff Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: query
 *         name: page
 *         schema:
 *           type: integer
 *           default: 1
 *       - in: query
 *         name: limit
 *         schema:
 *           type: integer
 *           default: 20
 *       - in: query
 *         name: keyword
 *         schema:
 *           type: string
 *       - in: query
 *         name: plan
 *         schema:
 *           type: string
 *           enum: [FREE, PRO]
 *       - in: query
 *         name: status
 *         schema:
 *           type: string
 *           enum: [NONE, ACTIVE, EXPIRED, CANCELLED]
 *       - in: query
 *         name: sort_by
 *         schema:
 *           type: string
 *           enum: [created_at, subscription_expires_at, plan]
 *       - in: query
 *         name: sort_order
 *         schema:
 *           type: string
 *           enum: [asc, desc]
 *     responses:
 *       200:
 *         description: List of subscriptions
 *       401:
 *         description: Unauthorized
 *       403:
 *         description: Forbidden
 */
router.get('/', listSubscriptionsRules, validate, staffSubscriptionsController.list);

/**
 * @openapi
 * /api/staff/subscriptions/search:
 *   get:
 *     summary: Search subscriptions by keyword
 *     description: Search users by email or full_name. Read-only for STAFF.
 *     tags: [Staff Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: query
 *         name: keyword
 *         required: true
 *         schema:
 *           type: string
 *       - in: query
 *         name: page
 *         schema:
 *           type: integer
 *       - in: query
 *         name: limit
 *         schema:
 *           type: integer
 *     responses:
 *       200:
 *         description: Search results
 *       401:
 *         description: Unauthorized
 *       403:
 *         description: Forbidden
 */
router.get('/search', staffSubscriptionsController.search);

/**
 * @openapi
 * /api/staff/subscriptions/{userId}:
 *   get:
 *     summary: Get subscription detail of a user (read-only)
 *     description: Returns basic user info and subscription details. No transaction history for STAFF.
 *     tags: [Staff Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: userId
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Subscription detail
 *       404:
 *         description: User not found
 *       401:
 *         description: Unauthorized
 *       403:
 *         description: Forbidden
 */
router.get('/:userId', staffSubscriptionsController.detail);

module.exports = router;
