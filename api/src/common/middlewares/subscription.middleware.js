const User = require('../../database/models/user.model');

/**
 * Middleware to check and enforce subscription expiry
 * Runs after auth.middleware - lazily checks and downgrades expired PRO subscriptions
 */
const checkSubscriptionExpiry = async (req, res, next) => {
    try {
        const user = req.user;

        // Only check PRO users
        if (user.plan !== 'PRO') {
            return next();
        }

        const now = new Date();
        const expiresAt = user.subscription_expires_at
            ? new Date(user.subscription_expires_at)
            : null;

        const isStatusExpired =
            user.subscription_status === 'EXPIRED' ||
            user.subscription_status === 'CANCELLED';

        const isDateExpired =
            user.subscription_status === 'ACTIVE' && expiresAt && expiresAt < now;

        if (isStatusExpired || isDateExpired) {
            // Downgrade to FREE
            user.plan = 'FREE';
            if (isDateExpired) {
                user.subscription_status = 'EXPIRED';
            }
            await user.save();

            // Update req.user with downgraded plan
            req.user.plan = 'FREE';
            req.user.subscription_status = user.subscription_status;

            console.log(
                `[Subscription] User ${user.email} downgraded to FREE ` +
                `(status: ${user.subscription_status}, expired: ${expiresAt?.toISOString() ?? 'N/A'})`
            );
        }

        next();
    } catch (error) {
        next(error);
    }
};

module.exports = {
    checkSubscriptionExpiry
};