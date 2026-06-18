const express = require('express');
const router = express.Router();

const adminSubscriptionsController = require('./admin-subscriptions.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const roleMiddleware = require('../../common/middlewares/role.middleware');
const {
  validate,
  listSubscriptionsRules,
  renewGrantValidation,
  cancelValidation,
  modifyExpiryValidation
} = require('./admin-subscriptions.validation');

// All routes require authentication + ADMIN role
router.use(authMiddleware);
router.use(roleMiddleware(['ADMIN']));

/**
 * @openapi
 * tags:
 *   - name: Admin Subscriptions
 *     description: ADMIN subscription management
 */

/**
 * @openapi
 * /api/admin/subscriptions:
 *   get:
 *     summary: List all subscriptions (paginated, filterable)
 *     description: Returns paginated list of users with subscription info and summary stats.
 *     tags: [Admin Subscriptions]
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
 *         description: Search by email or full_name
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
 *         name: role
 *         schema:
 *           type: string
 *           enum: [USER, STAFF, ADMIN]
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
 *         description: List of subscriptions with summary
 *       401:
 *         description: Unauthorized
 *       403:
 *         description: Forbidden (requires ADMIN)
 */
router.get('/', listSubscriptionsRules, validate, adminSubscriptionsController.list);

/**
 * @openapi
 * /api/admin/subscriptions/stats:
 *   get:
 *     summary: Get subscription dashboard stats
 *     description: Returns overview stats, revenue, expiring soon counts, and recent transactions.
 *     tags: [Admin Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Subscription stats
 *       401:
 *         description: Unauthorized
 *       403:
 *         description: Forbidden (requires ADMIN)
 */
router.get('/stats', adminSubscriptionsController.stats);

/**
 * @openapi
 * /api/admin/subscriptions/transactions:
 *   get:
 *     summary: Get transaction history
 *     description: Returns paginated list of all subscription transactions (PayOS + admin actions).
 *     tags: [Admin Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: query
 *         name: page
 *         schema:
 *           type: integer
 *       - in: query
 *         name: limit
 *         schema:
 *           type: integer
 *       - in: query
 *         name: user_id
 *         schema:
 *           type: string
 *       - in: query
 *         name: type
 *         schema:
 *           type: string
 *           enum: [PAYOS_PAYMENT, ADMIN_GRANT, ADMIN_RENEW, ADMIN_CANCEL, ADMIN_MODIFY]
 *       - in: query
 *         name: status
 *         schema:
 *           type: string
 *       - in: query
 *         name: from
 *         schema:
 *           type: string
 *           format: date
 *       - in: query
 *         name: to
 *         schema:
 *           type: string
 *           format: date
 *     responses:
 *       200:
 *         description: Transaction list
 *       401:
 *         description: Unauthorized
 *       403:
 *         description: Forbidden (requires ADMIN)
 */
router.get('/transactions', adminSubscriptionsController.transactions);

/**
 * @openapi
 * /api/admin/subscriptions/{userId}:
 *   get:
 *     summary: Get subscription detail of a user
 *     description: Returns user info, subscription details, and transaction history.
 *     tags: [Admin Subscriptions]
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
 *         description: Forbidden (requires ADMIN)
 */
router.get('/:userId', adminSubscriptionsController.detail);

/**
 * @openapi
 * /api/admin/subscriptions/{userId}/grant:
 *   post:
 *     summary: Grant PRO subscription to a FREE/EXPIRED user
 *     tags: [Admin Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: userId
 *         required: true
 *         schema:
 *           type: string
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - duration_days
 *             properties:
 *               duration_days:
 *                 type: integer
 *                 example: 30
 *               notes:
 *                 type: string
 *     responses:
 *       200:
 *         description: Subscription granted
 *       400:
 *         description: User already has active PRO
 *       404:
 *         description: User not found
 */
router.post('/:userId/grant', renewGrantValidation, validate, adminSubscriptionsController.grant);

/**
 * @openapi
 * /api/admin/subscriptions/{userId}/renew:
 *   post:
 *     summary: Renew PRO subscription (extend expiry)
 *     tags: [Admin Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: userId
 *         required: true
 *         schema:
 *           type: string
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - duration_days
 *             properties:
 *               duration_days:
 *                 type: integer
 *                 example: 30
 *               notes:
 *                 type: string
 *     responses:
 *       200:
 *         description: Subscription renewed
 *       404:
 *         description: User not found
 */
router.post('/:userId/renew', renewGrantValidation, validate, adminSubscriptionsController.renew);

/**
 * @openapi
 * /api/admin/subscriptions/{userId}/cancel:
 *   post:
 *     summary: Cancel PRO subscription (downgrade to FREE)
 *     tags: [Admin Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: userId
 *         required: true
 *         schema:
 *           type: string
 *     requestBody:
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               notes:
 *                 type: string
 *     responses:
 *       200:
 *         description: Subscription cancelled
 *       400:
 *         description: User does not have active PRO
 *       404:
 *         description: User not found
 */
router.post('/:userId/cancel', cancelValidation, validate, adminSubscriptionsController.cancel);

/**
 * @openapi
 * /api/admin/subscriptions/{userId}/expiry:
 *   patch:
 *     summary: Modify subscription expiry date
 *     tags: [Admin Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: userId
 *         required: true
 *         schema:
 *           type: string
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - expires_at
 *             properties:
 *               expires_at:
 *                 type: string
 *                 format: date-time
 *                 example: "2026-09-15T10:00:00.000Z"
 *               notes:
 *                 type: string
 *     responses:
 *       200:
 *         description: Expiry updated
 *       400:
 *         description: User is not on PRO
 *       404:
 *         description: User not found
 */
router.patch('/:userId/expiry', modifyExpiryValidation, validate, adminSubscriptionsController.modifyExpiry);

module.exports = router;
