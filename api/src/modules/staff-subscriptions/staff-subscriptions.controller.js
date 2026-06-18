const staffSubscriptionsService = require('./staff-subscriptions.service');
const { success } = require('../../common/utils/response.util');

/**
 * Format user object for subscription list response
 */
const formatUserSubscription = (user) => {
  const roleName = user.role_id?.name || 'USER';
  return {
    id: user._id.toString(),
    full_name: user.full_name,
    email: user.email,
    role: roleName,
    status: user.status,
    plan: user.plan || 'FREE',
    subscription_status: user.subscription_status || 'NONE',
    subscription_expires_at: user.subscription_expires_at || null,
    created_at: user.created_at
  };
};

/**
 * List subscriptions (read-only, no summary)
 */
const list = async (req, res, next) => {
  try {
    const result = await staffSubscriptionsService.listSubscriptions(req.query);
    const formattedItems = result.items.map(formatUserSubscription);
    return success(res, 'Get subscriptions successfully', {
      items: formattedItems,
      pagination: result.pagination
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get subscription detail of a user (basic info, no transactions)
 */
const detail = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const user = await staffSubscriptionsService.getSubscriptionDetail(userId);
    const roleName = user.role_id?.name || 'USER';
    return success(res, 'Get subscription detail successfully', {
      user: {
        id: user._id.toString(),
        full_name: user.full_name,
        email: user.email,
        role: roleName,
        status: user.status
      },
      subscription: {
        plan: user.plan || 'FREE',
        status: user.subscription_status || 'NONE',
        expires_at: user.subscription_expires_at || null
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Search subscriptions by keyword
 */
const search = async (req, res, next) => {
  try {
    const { keyword } = req.query;
    const result = await staffSubscriptionsService.searchSubscriptions(keyword, req.query);
    const formattedItems = result.items.map(formatUserSubscription);
    return success(res, 'Search subscriptions successfully', {
      items: formattedItems,
      pagination: result.pagination
    });
  } catch (error) {
    next(error);
  }
};

module.exports = {
  list,
  detail,
  search
};
