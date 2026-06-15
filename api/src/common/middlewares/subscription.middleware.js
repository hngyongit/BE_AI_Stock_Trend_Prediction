const User = require('../../database/models/user.model');

/**
 * Middleware to check and enforce subscription expiry
 * Runs after auth.middleware - lazily checks and downgrades expired PRO subscriptions
 */
const checkSubscriptionExpiry = async (req, res, next) => {
    try {
        const user = req.user;

        // Only check PRO users with ACTIVE subscription status
        if (user.plan === 'PRO' && user.subscription_status === 'ACTIVE') {
            const now = new Date();
            const expiresAt = user.subscription_expires_at ? new Date(user.subscription_expires_at) : null;

            if (expiresAt && expiresAt < now) {
                // Auto-downgrade to FREE
                user.plan = 'FREE';
                user.subscription_status = 'EXPIRED';
                await user.save();

                // Update req.user with downgraded plan
                req.user.plan = 'FREE';
                req.user.subscription_status = 'EXPIRED';
            }
        }

        next();
    } catch (error) {
        next(error);
    }
};

module.exports = {
    checkSubscriptionExpiry
};