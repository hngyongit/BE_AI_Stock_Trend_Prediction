const express = require('express');
const router = express.Router();

const subscriptionsController = require('./subscriptions.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const { checkSubscriptionExpiry } = require('../../common/middlewares/subscription.middleware');
const { validate, createPaymentValidation } = require('./subscriptions.validation');

/**
 * @openapi
 * tags:
 *   - name: Subscriptions
 *     description: Subscription and payment management
 */

/**
 * @openapi
 * /api/subscriptions/create-payment:
 *   post:
 *     summary: Create payment for subscription upgrade
 *     description: Creates a PayOS payment request and returns a checkout URL for the user to complete payment.
 *     tags: [Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       201:
 *         description: Payment created successfully.
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
 *                   example: Create payment successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     checkoutUrl:
 *                       type: string
 *                       example: https://pay.payos.vn/web/...
 *                     orderCode:
 *                       type: number
 *                     paymentLinkId:
 *                       type: string
 *                     amount:
 *                       type: number
 *       400:
 *         description: User already has active PRO subscription.
 *       401:
 *         description: Unauthorized.
 */
router.post('/create-payment', authMiddleware, checkSubscriptionExpiry, createPaymentValidation, validate, subscriptionsController.createPayment);

/**
 * @openapi
 * /api/subscriptions/webhook:
 *   post:
 *     summary: Handle PayOS webhook callback
 *     description: Receives webhook callbacks from PayOS after payment completion. This endpoint is public and does not require authentication.
 *     tags: [Subscriptions]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               orderCode:
 *                 type: number
 *               status:
 *                 type: string
 *                 example: PAID
 *     responses:
 *       200:
 *         description: Webhook processed successfully.
 */
router.post('/webhook', subscriptionsController.handleWebhook);

/**
 * @openapi
 * /api/subscriptions/status:
 *   get:
 *     summary: Get current subscription status
 *     description: Returns the user's current plan and subscription status.
 *     tags: [Subscriptions]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Subscription status retrieved successfully.
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
 *                   example: Get subscription status successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     plan:
 *                       type: string
 *                       example: FREE
 *                     subscriptionStatus:
 *                       type: string
 *                       example: NONE
 *                     subscriptionExpiresAt:
 *                       type: string
 *                       format: date-time
 *                       nullable: true
 *       401:
 *         description: Unauthorized.
 */
router.get('/status', authMiddleware, checkSubscriptionExpiry, subscriptionsController.getStatus);

/**
 * @openapi
 * /api/subscriptions/transactions:
 *   get:
 *     summary: Get my transaction history
 *     description: Returns paginated transaction history for the authenticated user.
 *     tags: [Subscriptions]
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
 *     responses:
 *       200:
 *         description: Transaction list
 *       401:
 *         description: Unauthorized
 */
router.get('/transactions', authMiddleware, subscriptionsController.getMyTransactions);

module.exports = router;