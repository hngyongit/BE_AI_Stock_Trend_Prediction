/**
 * Plan configuration for subscription-based features
 */

const PLAN_LIMITS = {
    FREE: {
        max_watchlist_items: 5
    },
    PRO: {
        max_watchlist_items: 50
    }
};

const SUBSCRIPTION_PRICE = 50000; // VND
const SUBSCRIPTION_DURATION_DAYS = 30;

module.exports = {
    PLAN_LIMITS,
    SUBSCRIPTION_PRICE,
    SUBSCRIPTION_DURATION_DAYS
};