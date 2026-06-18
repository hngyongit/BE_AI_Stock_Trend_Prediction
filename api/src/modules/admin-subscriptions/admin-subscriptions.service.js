const User = require('../../database/models/user.model');
const Role = require('../../database/models/role.model');
const SubscriptionTransaction = require('../../database/models/subscription-transaction.model');
const { SUBSCRIPTION_PRICE, SUBSCRIPTION_DURATION_DAYS } = require('../../config/plan.config');

/**
 * Admin: Get paginated subscription list with search/filter/summary
 */
const listSubscriptions = async (queries) => {
  const page = parseInt(queries.page || '1', 10);
  const limit = parseInt(queries.limit || '20', 10);
  const skip = (page - 1) * limit;

  const filter = {};

  // Keyword search (email, full_name)
  if (queries.keyword) {
    const searchRegex = { $regex: queries.keyword, $options: 'i' };
    filter.$or = [
      { full_name: searchRegex },
      { email: searchRegex }
    ];
  }

  // Plan filter
  if (queries.plan) {
    filter.plan = queries.plan;
  }

  // Subscription status filter
  if (queries.status) {
    filter.subscription_status = queries.status;
  }

  // Role filter
  if (queries.role) {
    const roleDoc = await Role.findOne({ name: queries.role.toUpperCase() });
    if (roleDoc) {
      filter.role_id = roleDoc._id;
    } else {
      return {
        items: [],
        pagination: { page, limit, total_items: 0, total_pages: 0 },
        summary: { total_users: 0, active_pro: 0, expired_pro: 0, cancelled_pro: 0, free_users: 0 }
      };
    }
  }

  // Sort
  const sortField = queries.sort_by || 'created_at';
  const sortOrder = queries.sort_order === 'asc' ? 1 : -1;

  const items = await User.find(filter)
    .populate('role_id')
    .sort({ [sortField]: sortOrder })
    .skip(skip)
    .limit(limit);

  const total_items = await User.countDocuments(filter);
  const total_pages = Math.ceil(total_items / limit);

  // Compute summary
  const allUsersCount = await User.countDocuments();
  const activePro = await User.countDocuments({ plan: 'PRO', subscription_status: 'ACTIVE' });
  const expiredPro = await User.countDocuments({ plan: 'PRO', subscription_status: 'EXPIRED' });
  const cancelledPro = await User.countDocuments({ plan: 'PRO', subscription_status: 'CANCELLED' });
  const freeUsers = await User.countDocuments({ plan: 'FREE' });

  return {
    items,
    pagination: { page, limit, total_items, total_pages },
    summary: {
      total_users: allUsersCount,
      active_pro: activePro,
      expired_pro: expiredPro,
      cancelled_pro: cancelledPro,
      free_users: freeUsers
    }
  };
};

/**
 * Admin: Get subscription detail of a specific user (with transaction history)
 */
const getSubscriptionDetail = async (adminId, userId) => {
  const user = await User.findById(userId).populate('role_id');
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  const transactions = await SubscriptionTransaction.find({ user_id: userId })
    .sort({ created_at: -1 })
    .limit(50);

  return { user, transactions };
};

/**
 * Admin: Grant PRO (for FREE/EXPIRED users only)
 */
const grantSubscription = async (adminId, userId, durationDays, notes) => {
  const user = await User.findById(userId);
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  if (user.plan === 'PRO' && user.subscription_status === 'ACTIVE') {
    const error = new Error('User already has an active PRO subscription. Use renew instead.');
    error.statusCode = 400;
    throw error;
  }

  const previousPlan = user.plan;
  const previousExpiresAt = user.subscription_expires_at;

  const expiresAt = new Date();
  expiresAt.setDate(expiresAt.getDate() + durationDays);

  user.plan = 'PRO';
  user.subscription_status = 'ACTIVE';
  user.subscription_expires_at = expiresAt;
  await user.save();

  await SubscriptionTransaction.create({
    user_id: user._id,
    transaction_type: 'ADMIN_GRANT',
    amount: 0,
    status: 'GRANTED',
    previous_plan: previousPlan,
    new_plan: 'PRO',
    previous_expires_at: previousExpiresAt,
    new_expires_at: expiresAt,
    performed_by: adminId,
    notes: notes || 'Admin granted PRO subscription'
  });

  return {
    user_id: user._id,
    plan: user.plan,
    subscription_status: user.subscription_status,
    subscription_expires_at: user.subscription_expires_at
  };
};

/**
 * Admin: Renew PRO subscription
 */
const renewSubscription = async (adminId, userId, durationDays, notes) => {
  const user = await User.findById(userId);
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  const previousPlan = user.plan;
  const previousExpiresAt = user.subscription_expires_at;

  let expiresAt;
  const now = new Date();

  if (user.plan === 'PRO' && user.subscription_status === 'ACTIVE' && user.subscription_expires_at) {
    // Extend from current expiry
    expiresAt = new Date(user.subscription_expires_at);
    expiresAt.setDate(expiresAt.getDate() + durationDays);
  } else {
    // If expired or FREE, start from now
    expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + durationDays);
  }

  user.plan = 'PRO';
  user.subscription_status = 'ACTIVE';
  user.subscription_expires_at = expiresAt;
  await user.save();

  await SubscriptionTransaction.create({
    user_id: user._id,
    transaction_type: 'ADMIN_RENEW',
    amount: 0,
    status: 'GRANTED',
    previous_plan: previousPlan,
    new_plan: 'PRO',
    previous_expires_at: previousExpiresAt,
    new_expires_at: expiresAt,
    performed_by: adminId,
    notes: notes || `Admin renewed subscription for ${durationDays} days`
  });

  return {
    user_id: user._id,
    plan: user.plan,
    subscription_status: user.subscription_status,
    subscription_expires_at: user.subscription_expires_at,
    duration_days: durationDays
  };
};

/**
 * Admin: Cancel PRO subscription (downgrade to FREE)
 */
const cancelSubscription = async (adminId, userId, notes) => {
  const user = await User.findById(userId);
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  if (user.plan !== 'PRO' || user.subscription_status !== 'ACTIVE') {
    const error = new Error('User does not have an active PRO subscription to cancel');
    error.statusCode = 400;
    throw error;
  }

  const previousPlan = user.plan;
  const previousExpiresAt = user.subscription_expires_at;

  user.plan = 'FREE';
  user.subscription_status = 'CANCELLED';
  user.subscription_expires_at = null;
  await user.save();

  await SubscriptionTransaction.create({
    user_id: user._id,
    transaction_type: 'ADMIN_CANCEL',
    amount: 0,
    status: 'CANCELLED',
    previous_plan: previousPlan,
    new_plan: 'FREE',
    previous_expires_at: previousExpiresAt,
    new_expires_at: null,
    performed_by: adminId,
    notes: notes || 'Admin cancelled subscription'
  });

  return {
    user_id: user._id,
    plan: user.plan,
    subscription_status: user.subscription_status,
    subscription_expires_at: user.subscription_expires_at
  };
};

/**
 * Admin: Modify subscription expiry date
 */
const modifyExpiry = async (adminId, userId, expiresAt, notes) => {
  const user = await User.findById(userId);
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }

  if (user.plan !== 'PRO') {
    const error = new Error('User is not on PRO plan');
    error.statusCode = 400;
    throw error;
  }

  const previousPlan = user.plan;
  const previousExpiresAt = user.subscription_expires_at;
  const newExpiresAt = new Date(expiresAt);

  user.subscription_expires_at = newExpiresAt;
  await user.save();

  await SubscriptionTransaction.create({
    user_id: user._id,
    transaction_type: 'ADMIN_MODIFY',
    amount: 0,
    status: 'GRANTED',
    previous_plan: previousPlan,
    new_plan: 'PRO',
    previous_expires_at: previousExpiresAt,
    new_expires_at: newExpiresAt,
    performed_by: adminId,
    notes: notes || 'Admin modified subscription expiry'
  });

  return {
    user_id: user._id,
    plan: user.plan,
    subscription_status: user.subscription_status,
    subscription_expires_at: user.subscription_expires_at
  };
};

/**
 * Admin: Get subscription stats / dashboard
 */
const getStats = async () => {
  const totalUsers = await User.countDocuments();
  const activePro = await User.countDocuments({ plan: 'PRO', subscription_status: 'ACTIVE' });
  const expiredPro = await User.countDocuments({ plan: 'PRO', subscription_status: 'EXPIRED' });
  const cancelledPro = await User.countDocuments({ plan: 'PRO', subscription_status: 'CANCELLED' });
  const freeUsers = await User.countDocuments({ plan: 'FREE' });
  const proPercentage = totalUsers > 0 ? parseFloat(((activePro / totalUsers) * 100).toFixed(1)) : 0;

  // Expiring soon
  const now = new Date();
  const in7Days = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  const in30Days = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);

  const within7Days = await User.countDocuments({
    plan: 'PRO',
    subscription_status: 'ACTIVE',
    subscription_expires_at: { $gte: now, $lte: in7Days }
  });
  const within30Days = await User.countDocuments({
    plan: 'PRO',
    subscription_status: 'ACTIVE',
    subscription_expires_at: { $gte: now, $lte: in30Days }
  });

  // Revenue
  const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const firstOfLastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);

  const currentMonthRevenue = await SubscriptionTransaction.aggregate([
    { $match: { status: 'PAID', created_at: { $gte: firstOfMonth } } },
    { $group: { _id: null, total: { $sum: '$amount' } } }
  ]);

  const lastMonthRevenue = await SubscriptionTransaction.aggregate([
    { $match: { status: 'PAID', created_at: { $gte: firstOfLastMonth, $lt: firstOfMonth } } },
    { $group: { _id: null, total: { $sum: '$amount' } } }
  ]);

  const totalAllTime = await SubscriptionTransaction.aggregate([
    { $match: { status: 'PAID' } },
    { $group: { _id: null, total: { $sum: '$amount' } } }
  ]);

  // Recent transactions
  const recentTransactions = await SubscriptionTransaction.find()
    .populate('user_id', 'full_name email')
    .sort({ created_at: -1 })
    .limit(10);

  return {
    overview: {
      total_users: totalUsers,
      active_pro: activePro,
      expired_pro: expiredPro,
      cancelled_pro: cancelledPro,
      free_users: freeUsers,
      pro_percentage: proPercentage
    },
    expiring_soon: {
      within_7_days: within7Days,
      within_30_days: within30Days
    },
    revenue: {
      current_month: currentMonthRevenue.length > 0 ? currentMonthRevenue[0].total : 0,
      last_month: lastMonthRevenue.length > 0 ? lastMonthRevenue[0].total : 0,
      total_all_time: totalAllTime.length > 0 ? totalAllTime[0].total : 0,
      currency: 'VND'
    },
    recent_transactions: recentTransactions
  };
};

/**
 * Admin: Get transaction history (paginated, filterable)
 */
const getTransactions = async (queries) => {
  const page = parseInt(queries.page || '1', 10);
  const limit = parseInt(queries.limit || '20', 10);
  const skip = (page - 1) * limit;

  const filter = {};

  if (queries.user_id) {
    filter.user_id = queries.user_id;
  }
  if (queries.type) {
    filter.transaction_type = queries.type;
  }
  if (queries.status) {
    filter.status = queries.status;
  }
  if (queries.from || queries.to) {
    filter.created_at = {};
    if (queries.from) {
      filter.created_at.$gte = new Date(queries.from);
    }
    if (queries.to) {
      filter.created_at.$lte = new Date(queries.to);
    }
  }

  const items = await SubscriptionTransaction.find(filter)
    .populate('user_id', 'full_name email')
    .populate('performed_by', 'full_name email')
    .sort({ created_at: -1 })
    .skip(skip)
    .limit(limit);

  const total_items = await SubscriptionTransaction.countDocuments(filter);
  const total_pages = Math.ceil(total_items / limit);

  return {
    items,
    pagination: { page, limit, total_items, total_pages }
  };
};

module.exports = {
  listSubscriptions,
  getSubscriptionDetail,
  grantSubscription,
  renewSubscription,
  cancelSubscription,
  modifyExpiry,
  getStats,
  getTransactions
};
