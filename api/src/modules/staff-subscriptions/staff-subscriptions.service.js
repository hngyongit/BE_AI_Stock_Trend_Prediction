const User = require('../../database/models/user.model');
const Role = require('../../database/models/role.model');

/**
 * Staff: Get paginated subscription list (read-only, no summary)
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
        pagination: { page, limit, total_items: 0, total_pages: 0 }
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

  return {
    items,
    pagination: { page, limit, total_items, total_pages }
  };
};

/**
 * Staff: Get subscription detail of a specific user (basic info only, no transactions)
 */
const getSubscriptionDetail = async (userId) => {
  const user = await User.findById(userId).populate('role_id');
  if (!user) {
    const error = new Error('User not found');
    error.statusCode = 404;
    throw error;
  }
  return user;
};

/**
 * Staff: Search subscriptions by keyword
 */
const searchSubscriptions = async (keyword, queries) => {
  const page = parseInt(queries.page || '1', 10);
  const limit = parseInt(queries.limit || '20', 10);
  const skip = (page - 1) * limit;

  if (!keyword || keyword.trim() === '') {
    return {
      items: [],
      pagination: { page, limit, total_items: 0, total_pages: 0 }
    };
  }

  const searchRegex = { $regex: keyword, $options: 'i' };
  const filter = {
    $or: [
      { full_name: searchRegex },
      { email: searchRegex }
    ]
  };

  const items = await User.find(filter)
    .populate('role_id')
    .sort({ created_at: -1 })
    .skip(skip)
    .limit(limit);

  const total_items = await User.countDocuments(filter);
  const total_pages = Math.ceil(total_items / limit);

  return {
    items,
    pagination: { page, limit, total_items, total_pages }
  };
};

module.exports = {
  listSubscriptions,
  getSubscriptionDetail,
  searchSubscriptions
};
