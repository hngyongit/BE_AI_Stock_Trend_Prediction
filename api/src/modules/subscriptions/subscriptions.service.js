const User = require('../../database/models/user.model');
const payosService = require('./payos.service');
const { SUBSCRIPTION_PRICE, SUBSCRIPTION_DURATION_DAYS } = require('../../config/plan.config');
const env = require('../../config/env.config');

/**
 * Create a payment request for subscription upgrade
 * @param {string} userId - User ID
 * @returns {Promise<Object>} - { checkoutUrl, orderCode, paymentLinkId, amount }
 */
const createPayment = async (userId) => {
    const user = await User.findById(userId);
    if (!user) {
        const error = new Error('User not found');
        error.statusCode = 404;
        throw error;
    }

    // Check if user is already PRO
    if (user.plan === 'PRO' && user.subscription_status === 'ACTIVE') {
        const error = new Error('User is already on PRO plan');
        error.statusCode = 400;
        throw error;
    }

    // Generate unique order code
    const orderCode = parseInt(`${Date.now()}${userId.toString().slice(-4)}`, 10);

    // Build items array (required by PayOS)
    const items = [
        {
            name: 'Gói PRO 30 ngày',
            quantity: 1,
            price: SUBSCRIPTION_PRICE
        }
    ];

    // Get URLs from env
    const returnUrl = env.PAYOS_RETURN_URL || 'http://localhost:3000/payment/success';
    const cancelUrl = env.PAYOS_CANCEL_URL || 'http://localhost:3000/payment/cancel';

    // Create payment request
    const paymentResult = await payosService.createPaymentRequest({
        orderCode,
        amount: SUBSCRIPTION_PRICE,
        description: 'Nâng cấp PRO',
        returnUrl,
        cancelUrl,
        items
    });

    // Save PayOS data on user document
    user.payos_order_code = orderCode;
    user.payos_payment_link_id = paymentResult.paymentLinkId;
    await user.save();

    return {
        checkoutUrl: paymentResult.checkoutUrl,
        orderCode: paymentResult.orderCode,
        paymentLinkId: paymentResult.paymentLinkId,
        amount: SUBSCRIPTION_PRICE
    };
};

/**
 * Handle PayOS webhook callback
 * @param {Object} webhookPayload - Verified webhook payload
 * @returns {Promise<Object>} - Updated user subscription info
 */
const handlePaymentWebhook = async (webhookPayload) => {
    const { orderCode, status } = webhookPayload;

    // Find user by order code
    const user = await User.findOne({ payos_order_code: orderCode });
    if (!user) {
        const error = new Error('User not found for this payment');
        error.statusCode = 404;
        throw error;
    }

    // Only process successful payments
    if (status !== 'PAID') {
        return {
            userId: user._id,
            plan: user.plan,
            subscriptionStatus: user.subscription_status
        };
    }

    // Calculate expiry date
    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + SUBSCRIPTION_DURATION_DAYS);

    // Upgrade user
    user.plan = 'PRO';
    user.subscription_status = 'ACTIVE';
    user.subscription_expires_at = expiresAt;
    await user.save();

    return {
        userId: user._id,
        plan: user.plan,
        subscriptionStatus: user.subscription_status,
        subscriptionExpiresAt: user.subscription_expires_at
    };
};

/**
 * Get current subscription status for a user
 * @param {string} userId - User ID
 * @returns {Promise<Object>}
 */
const getSubscriptionStatus = async (userId) => {
    const user = await User.findById(userId);
    if (!user) {
        const error = new Error('User not found');
        error.statusCode = 404;
        throw error;
    }

    return {
        plan: user.plan || 'FREE',
        subscriptionStatus: user.subscription_status || 'NONE',
        subscriptionExpiresAt: user.subscription_expires_at || null
    };
};

module.exports = {
    createPayment,
    handlePaymentWebhook,
    getSubscriptionStatus
};