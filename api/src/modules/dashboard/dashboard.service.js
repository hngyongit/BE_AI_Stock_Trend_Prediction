const dashboardRepository = require('./dashboard.repository');

/**
 * Service to process and return USER dashboard information.
 */
const getUserDashboard = async (userId) => {
  const [watchlistItems, marketLeaders, marketOverview] = await Promise.all([
    dashboardRepository.findUserWatchlistWithPrice(userId),
    dashboardRepository.findMarketLeaders(),
    dashboardRepository.findLatestMarketOverview()
  ]);

  let gainers = 0;
  let losers = 0;
  let flat = 0;

  for (const item of watchlistItems) {
    if (item.latest_price) {
      const change = item.latest_price.price_change;
      if (change > 0) {
        gainers++;
      } else if (change < 0) {
        losers++;
      } else {
        flat++;
      }
    } else {
      flat++;
    }
  }

  return {
    watchlist: {
      total_stocks: watchlistItems.length,
      items: watchlistItems,
      trends: {
        gainers,
        losers,
        flat
      }
    },
    market_leaders: marketLeaders,
    market_overview: marketOverview
  };
};

/**
 * Service to process and return STAFF dashboard information.
 */
const getStaffDashboard = async () => {
  return dashboardRepository.findCrawlStats();
};

/**
 * Service to process and return ADMIN dashboard information.
 */
const getAdminDashboard = async () => {
  const [adminStats, crawlStats] = await Promise.all([
    dashboardRepository.findAdminStats(),
    dashboardRepository.findCrawlStats()
  ]);

  return {
    users: adminStats.users,
    watchlists: adminStats.watchlists,
    catalog: adminStats.catalog,
    system_health: {
      crawl_success_rate_percent: crawlStats.logs.success_rate_percent,
      total_crawl_runs: crawlStats.logs.total_runs
    }
  };
};

module.exports = {
  getUserDashboard,
  getStaffDashboard,
  getAdminDashboard
};
