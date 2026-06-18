const adminSubscriptionsService = require('./admin-subscriptions.service');
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
 * ADSUB-01: List subscriptions (paginated, filterable)
 */
const list = async (req, res, next) => {
  try {
    const result = await adminSubscriptionsService.listSubscriptions(req.query);
    const formattedItems = result.items.map(formatUserSubscription);
    return success(res, 'Get subscriptions successfully', {
      items: formattedItems,
      pagination: result.pagination,
      summary: result.summary
    });
  } catch (error) {
    next(error);
  }
};

/**
 * ADSUB-02: Get subscription detail of a user
 */
const detail = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const result = await adminSubscriptionsService.getSubscriptionDetail(req.user._id, userId);
    const roleName = result.user.role_id?.name || 'USER';
    return success(res, 'Get subscription detail successfully', {
      user: {
        id: result.user._id.toString(),
        full_name: result.user.full_name,
        email: result.user.email,
        role: roleName,
        status: result.user.status
      },
      subscription: {
        plan: result.user.plan || 'FREE',
        status: result.user.subscription_status || 'NONE',
        expires_at: result.user.subscription_expires_at || null,
        payos_order_code: result.user.payos_order_code || null,
        payos_payment_link_id: result.user.payos_payment_link_id || null
      },
      transactions: result.transactions.map(t => ({
        id: t._id.toString(),
        type: t.transaction_type,
        amount: t.amount,
        status: t.status,
        notes: t.notes,
        created_at: t.created_at
      }))
    });
  } catch (error) {
    next(error);
  }
};

/**
 * ADSUB-06: Grant PRO (for FREE/EXPIRED users)
 */
const grant = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const { duration_days, notes } = req.body;
    const result = await adminSubscriptionsService.grantSubscription(
      req.user._id, userId, duration_days, notes
    );
    return success(res, 'Subscription granted successfully', result);
  } catch (error) {
    next(error);
  }
};

/**
 * ADSUB-06: Renew PRO subscription
 */
const renew = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const { duration_days, notes } = req.body;
    const result = await adminSubscriptionsService.renewSubscription(
      req.user._id, userId, duration_days, notes
    );
    return success(res, 'Subscription renewed successfully', result);
  } catch (error) {
    next(error);
  }
};

/**
 * ADSUB-07: Cancel PRO subscription
 */
const cancel = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const { notes } = req.body;
    const result = await adminSubscriptionsService.cancelSubscription(
      req.user._id, userId, notes
    );
    return success(res, 'Subscription cancelled successfully', result);
  } catch (error) {
    next(error);
  }
};

/**
 * ADSUB-08: Modify subscription expiry
 */
const modifyExpiry = async (req, res, next) => {
  try {
    const { userId } = req.params;
    const { expires_at, notes } = req.body;
    const result = await adminSubscriptionsService.modifyExpiry(
      req.user._id, userId, expires_at, notes
    );
    return success(res, 'Subscription expiry updated successfully', result);
  } catch (error) {
    next(error);
  }
};

/**
 * ADSUB-04: Get subscription stats / dashboard
 */
const stats = async (req, res, next) => {
  try {
    const result = await adminSubscriptionsService.getStats();
    return success(res, 'Get subscription stats successfully', result);
  } catch (error) {
    next(error);
  }
};

/**
 * ADSUB-05: Get transaction history
 */
const transactions = async (req, res, next) => {
  try {
    const result = await adminSubscriptionsService.getTransactions(req.query);
    return success(res, 'Get transactions successfully', result);
  } catch (error) {
    next(error);
  }
};

module.exports = {
  list,
  detail,
  grant,
  renew,
  cancel,
  modifyExpiry,
  stats,
  transactions
};
