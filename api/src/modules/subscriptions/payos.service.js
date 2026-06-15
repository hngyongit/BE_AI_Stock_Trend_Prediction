const { PayOS } = require('@payos/node');
const env = require('../../config/env.config');

let payOSInstance = null;

/**
 * Get or create PayOS client instance
 * @returns {PayOS} PayOS client instance
 */
const getPayOSClient = () => {
    if (!payOSInstance) {
        payOSInstance = new PayOS({
            clientId: env.PAYOS_CLIENT_ID,
            apiKey: env.PAYOS_API_KEY,
            checksumKey: env.PAYOS_CHECKSUM_KEY
        });
    }
    return payOSInstance;
};

/**
 * Create a payment request with PayOS
 * @param {Object} params - Payment parameters
 * @param {number} params.orderCode - Unique order code
 * @param {number} params.amount - Amount in VND
 * @param {string} params.description - Payment description
 * @param {string} params.returnUrl - URL to redirect after success
 * @param {string} params.cancelUrl - URL to redirect after cancellation
 * @param {Array} params.items - Array of items (required by PayOS)
 * @returns {Promise<Object>} - { checkoutUrl, paymentLinkId, orderCode }
 */
const createPaymentRequest = async ({ orderCode, amount, description, returnUrl, cancelUrl, items }) => {
    const payOS = getPayOSClient();

    const paymentData = {
        orderCode,
        amount,
        description,
        items,
        cancelUrl,
        returnUrl
    };

    const paymentLink = await payOS.paymentRequests.create(paymentData);

    return {
        checkoutUrl: paymentLink.checkoutUrl,
        paymentLinkId: paymentLink.paymentLinkId,
        orderCode: paymentLink.orderCode
    };
};

/**
 * Verify webhook payload from PayOS
 * @param {Object} rawBody - Raw request body (not parsed JSON)
 * @returns {Object} - Verified webhook payload
 */
const verifyWebhook = (rawBody) => {
    const payOS = getPayOSClient();
    return payOS.webhooks.verify(rawBody);
};

module.exports = {
    getPayOSClient,
    createPaymentRequest,
    verifyWebhook
};