const User = require('../../database/models/user.model');
const Role = require('../../database/models/role.model');
const Watchlist = require('../../database/models/watchlist.model');
const FactMarketPrice = require('../../database/models/fact-market-price.model');
const FactMarketOverview = require('../../database/models/fact-market-overview.model');
const CrawlJob = require('../../database/models/crawl-job.model');
const CrawlLog = require('../../database/models/crawl-log.model');
const DimStock = require('../../database/models/dim-stock.model');
const DimMarket = require('../../database/models/dim-market.model');
const FactCrawlQuality = require('../../database/models/fact-crawl-quality.model');
const CrawlLogDetail = require('../../database/models/crawl-log-detail.model');
const DimStockDataSource = require('../../database/models/dim-stock-data-source.model');

/**
 * Fetch watchlist items for a specific user, including the latest price metrics.
 */
const findUserWatchlistWithPrice = async (userId) => {
  const entries = await Watchlist.find({ user_id: userId })
    .populate({
      path: 'stock_id',
      select: '_id symbol company_name market_id status',
      populate: {
        path: 'market_id',
        select: 'code name'
      }
    })
    .lean();

  const formattedWatchlist = [];
  for (const entry of entries) {
    if (!entry.stock_id) continue;

    const latestPrice = await FactMarketPrice.findOne({ stock_id: entry.stock_id._id })
      .sort({ time_id: -1 })
      .lean();

    formattedWatchlist.push({
      watchlist_id: entry._id.toString(),
      stock: {
        id: entry.stock_id._id.toString(),
        symbol: entry.stock_id.symbol,
        company_name: entry.stock_id.company_name,
        market_code: entry.stock_id.market_id ? entry.stock_id.market_id.code : '',
        status: entry.stock_id.status
      },
      latest_price: latestPrice ? {
        close_price: latestPrice.close_price,
        price_change: latestPrice.price_change || 0,
        price_change_percent: latestPrice.price_change_percent || 0,
        volume: latestPrice.volume,
        time_id: latestPrice.time_id
      } : null,
      created_at: entry.created_at
    });
  }
  return formattedWatchlist;
};

/**
 * Fetch top 5 gainers and top 5 losers for the latest trading day.
 */
const findMarketLeaders = async () => {
  const latestPriceRecord = await FactMarketPrice.findOne().sort({ time_id: -1 }).lean();
  const latestTimeId = latestPriceRecord ? latestPriceRecord.time_id : null;

  if (!latestTimeId) {
    return { gainers: [], losers: [] };
  }

  const gainersQuery = { time_id: latestTimeId, price_change_percent: { $gt: 0 } };
  const losersQuery = { time_id: latestTimeId, price_change_percent: { $lt: 0 } };

  const [gainers, losers] = await Promise.all([
    FactMarketPrice.find(gainersQuery)
      .sort({ price_change_percent: -1 })
      .limit(5)
      .populate({
        path: 'stock_id',
        select: 'symbol company_name'
      })
      .lean(),
    FactMarketPrice.find(losersQuery)
      .sort({ price_change_percent: 1 })
      .limit(5)
      .populate({
        path: 'stock_id',
        select: 'symbol company_name'
      })
      .lean()
  ]);



  const mapLeader = (p) => ({
    symbol: p.stock_id ? p.stock_id.symbol : 'UNKNOWN',
    company_name: p.stock_id ? p.stock_id.company_name : 'Unknown Company',
    close_price: p.close_price,
    price_change: p.price_change || 0,
    price_change_percent: p.price_change_percent || 0,
    volume: p.volume
  });

  return {
    latest_trading_date: latestTimeId,
    gainers: gainers.map(mapLeader),
    losers: losers.map(mapLeader)
  };
};

/**
 * Fetch general statistics of crawl jobs and logs for staffing dashboards.
 */
const findCrawlStats = async () => {
  const [totalJobs, activeJobs, totalLogs, statusCounts, recordsSum, recentLogs] = await Promise.all([
    CrawlJob.countDocuments(),
    CrawlJob.countDocuments({ status: 'active' }),
    CrawlLog.countDocuments(),
    CrawlLog.aggregate([
      { $group: { _id: '$status', count: { $sum: 1 } } }
    ]),
    CrawlLog.aggregate([
      {
        $group: {
          _id: null,
          fetched: { $sum: '$records_fetched' },
          inserted: { $sum: '$records_inserted' },
          updated: { $sum: '$records_updated' },
          failed: { $sum: '$records_failed' }
        }
      }
    ]),
    CrawlLog.find()
      .sort({ started_at: -1 })
      .limit(5)
      .populate({
        path: 'crawl_job_id',
        select: 'job_name data_type'
      })
      .lean()
  ]);

  // Extract counts by status
  const successCount = (statusCounts.find(s => s._id === 'SUCCESS') || { count: 0 }).count;
  const partialSuccessCount = (statusCounts.find(s => s._id === 'PARTIAL_SUCCESS') || { count: 0 }).count;
  const successRate = totalLogs > 0 ? ((successCount + partialSuccessCount) / totalLogs) * 100 : 0;

  const totals = recordsSum[0] || { fetched: 0, inserted: 0, updated: 0, failed: 0 };

  const [totalStocks, totalMarkets, totalSources] = await Promise.all([
    DimStock.countDocuments(),
    DimMarket.countDocuments(),
    DimStockDataSource.countDocuments()
  ]);

  // ETL status: latest run status per data_type
  const latestCrawlLogs = await CrawlLog.aggregate([
    { $sort: { started_at: -1 } },
    {
      $lookup: {
        from: 'crawlJobs',
        localField: 'crawl_job_id',
        foreignField: '_id',
        as: 'job'
      }
    },
    { $unwind: { path: '$job', preserveNullAndEmptyArrays: true } },
    { $match: { 'job.data_type': { $ne: null } } },
    {
      $group: {
        _id: '$job.data_type',
        latest_status: { $first: '$status' },
        latest_run: { $first: '$started_at' },
        log_id: { $first: '$_id' }
      }
    }
  ]);

  // Data quality summary from FactCrawlQuality
  const qualityAgg = await FactCrawlQuality.aggregate([
    {
      $group: {
        _id: null,
        avg_success_rate: { $avg: '$success_rate' },
        total_failed: { $sum: '$records_failed' }
      }
    }
  ]);

  const totalFailedSymbols = await CrawlLogDetail.countDocuments({ status: 'FAILED' });

  const qualitySummary = qualityAgg[0] || { avg_success_rate: 0, total_failed: 0 };

  // Database status: count documents from known collections
  const knownCollections = ['users', 'dimstocks', 'dimMarkets', 'crawlLogs', 'crawlJobs', 'watchlists'];
  let totalKnownDocs = 0;
  try {
    for (const colName of knownCollections) {
      const count = await mongoose.connection.db.collection(colName).countDocuments();
      totalKnownDocs += count;
    }
  } catch (_) {
    // Silently fail — some collections may not exist yet
  }

  return {
    jobs: {
      total: totalJobs,
      active: activeJobs,
      inactive: totalJobs - activeJobs
    },
    logs: {
      total_runs: totalLogs,
      success_rate_percent: Number(successRate.toFixed(2)),
      records_fetched: totals.fetched || 0,
      records_inserted: totals.inserted || 0,
      records_updated: totals.updated || 0,
      records_failed: totals.failed || 0
    },
    catalog: {
      total_stocks: totalStocks,
      total_markets: totalMarkets,
      total_data_sources: totalSources
    },
    recent_activities: recentLogs.map(log => ({
      log_id: log._id.toString(),
      job_name: log.crawl_job_id ? log.crawl_job_id.job_name : 'Manual/Deleted Job',
      data_type: log.crawl_job_id ? log.crawl_job_id.data_type : 'N/A',
      started_at: log.started_at,
      ended_at: log.ended_at || null,
      status: log.status,
      records_processed: (log.records_inserted || 0) + (log.records_updated || 0),
      error_message: log.error_message || null
    })),
    etl_status: latestCrawlLogs.map(e => ({
      data_type: e._id,
      latest_status: e.latest_status,
      latest_run: e.latest_run
    })),
    data_quality: {
      avg_success_rate_percent: Number((qualitySummary.avg_success_rate || 0).toFixed(2)),
      total_records_failed: qualitySummary.total_failed || 0,
      total_failed_symbols: totalFailedSymbols
    },
    database_status: {
      known_collections: knownCollections.length,
      total_documents: totalKnownDocs
    }
  };
};

/**
 * Fetch database-wide statistics for the admin dashboard.
 */
const findAdminStats = async () => {
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

  const [totalUsers, activeUsers, lockedUsers, newUsersCount, totalWatchlists, uniqueWatchlistUsers] = await Promise.all([
    User.countDocuments(),
    User.countDocuments({ status: 'ACTIVE' }),
    User.countDocuments({ status: 'LOCKED' }),
    User.countDocuments({ created_at: { $gte: sevenDaysAgo } }),
    Watchlist.countDocuments(),
    Watchlist.distinct('user_id')
  ]);

  // Role distribution
  const roles = await Role.find().lean();
  const roleDistribution = {};
  for (const role of roles) {
    const count = await User.countDocuments({ role_id: role._id });
    roleDistribution[role.name] = count;
  }

  const activeWatchlistUsersCount = uniqueWatchlistUsers.length;
  const averagePerUser = activeWatchlistUsersCount > 0 ? (totalWatchlists / activeWatchlistUsersCount) : 0;

  const [totalStocks, totalMarkets] = await Promise.all([
    DimStock.countDocuments(),
    DimMarket.countDocuments()
  ]);

  return {
    users: {
      total: totalUsers,
      active: activeUsers,
      locked: lockedUsers,
      new_registrations_last_7_days: newUsersCount,
      by_role: roleDistribution
    },
    watchlists: {
      total_entries: totalWatchlists,
      active_users_count: activeWatchlistUsersCount,
      average_per_user: Number(averagePerUser.toFixed(2))
    },
    catalog: {
      total_stocks: totalStocks,
      total_markets: totalMarkets
    }
  };
};

/**
 * Fetch the latest market overview statistics, including a 30-day chart history.
 */
const findLatestMarketOverview = async () => {
  // Get all unique index symbols (e.g. 'VNINDEX')
  const symbols = await FactMarketOverview.distinct('symbol');
  const results = [];

  for (const symbol of symbols) {
    const latestRecord = await FactMarketOverview.findOne({ symbol })
      .sort({ time_id: -1 })
      .lean();

    if (!latestRecord) continue;

    // Fetch last 30 historical records
    const history = await FactMarketOverview.find({ symbol })
      .sort({ time_id: -1 })
      .limit(30)
      .lean();

    // Reverse history to ascending (chronological) order for chart plotting
    const chartData = history.reverse().map(h => {
      const timeStr = String(h.time_id);
      const dateStr = `${timeStr.slice(0, 4)}-${timeStr.slice(4, 6)}-${timeStr.slice(6, 8)}`;
      return {
        date: dateStr,
        close: h.close_index,
        open: h.open_index,
        high: h.high_index,
        low: h.low_index,
        volume: h.total_volume || 0
      };
    });

    const timeStr = String(latestRecord.time_id);
    const dateStr = `${timeStr.slice(0, 4)}-${timeStr.slice(4, 6)}-${timeStr.slice(6, 8)}`;

    results.push({
      symbol: latestRecord.symbol,
      display_symbol: latestRecord.display_symbol || latestRecord.symbol,
      market: latestRecord.market || 'HOSE',
      close_index: latestRecord.close_index,
      open_index: latestRecord.open_index,
      high_index: latestRecord.high_index,
      low_index: latestRecord.low_index,
      change_value: latestRecord.change_value || 0,
      change_percent: latestRecord.change_percent || 0,
      total_volume: latestRecord.total_volume || 0,
      trading_date: dateStr,
      chart: chartData
    });
  }

  return results;
};

module.exports = {
  findUserWatchlistWithPrice,
  findMarketLeaders,
  findCrawlStats,
  findAdminStats,
  findLatestMarketOverview
};
