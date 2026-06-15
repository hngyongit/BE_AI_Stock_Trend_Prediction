const subscriptionsService = require('./subscriptions.service');
const payosService = require('./payos.service');
const { success } = require('../../common/utils/response.util');

/**
 * Create payment for subscription upgrade
 */
const createPayment = async (req, res, next) => {
    try {
        const userId = req.user._id || req.user.id;
        const result = await subscriptionsService.createPayment(userId);
        return success(res, 'Create payment successfully', result, 201);
    } catch (error) {
        next(error);
    }
};

/**
 * Handle PayOS webhook callback
 *
 * Supports two formats:
 * 1. PayOS real webhook:  { data: { orderCode, status, ... }, signature: "..." }
 * 2. Direct test/simplified: { orderCode, status }  (no verification)
 */
const handleWebhook = async (req, res, next) => {
    try {
        // Get raw body — may be Buffer (from express.raw) or already-parsed JS object
        const rawBody = req.body;

        // Normalize to a JS object
        let payload;
        if (Buffer.isBuffer(rawBody)) {
            payload = JSON.parse(rawBody.toString('utf8'));
        } else if (typeof rawBody === 'object' && rawBody !== null) {
            payload = rawBody;
        } else {
            throw new Error('Unexpected webhook body format');
        }

        // Determine if this is a PayOS webhook format { data, signature }
        // or a direct simplified format { orderCode, status }
        let webhookData;
        if (payload.data && payload.signature) {
            // Full PayOS format — verify signature
            webhookData = payosService.verifyWebhook(payload);
        } else if (payload.orderCode) {
            // Simplified format — use directly (for testing / manual use)
            webhookData = payload;
        } else {
            throw new Error('Invalid webhook payload: missing required fields');
        }

        // Handle payment
        const result = await subscriptionsService.handlePaymentWebhook(webhookData);

        return res.status(200).json({
            success: true,
            message: 'Webhook processed successfully',
            data: result
        });
    } catch (error) {
        // Log error but don't throw - webhook should always return 200 to PayOS
        console.error('Webhook error:', error.message);
        return res.status(200).json({
            success: false,
            message: 'Webhook processed with error',
            error: error.message
        });
    }
};

/**
 * Get current subscription status
 */
const getStatus = async (req, res, next) => {
    try {
        const userId = req.user._id || req.user.id;
        const result = await subscriptionsService.getSubscriptionStatus(userId);
        return success(res, 'Get subscription status successfully', result);
    } catch (error) {
        next(error);
    }
};

module.exports = {
    createPayment,
    handleWebhook,
    getStatus
};