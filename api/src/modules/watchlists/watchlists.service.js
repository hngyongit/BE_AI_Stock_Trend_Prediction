const watchlistsRepository = require('./watchlists.repository');
const DimStock = require('../../database/models/dim-stock.model');
const FactMarketPrice = require('../../database/models/fact-market-price.model');

const getUserWatchlist = async (userId) => {
  const entries = await watchlistsRepository.findUserWatchlist(userId);

  const result = [];
  for (const entry of entries) {
    if (!entry.stock_id) continue;

    const latestPrice = await FactMarketPrice.findOne({ stock_id: entry.stock_id._id })
      .sort({ time_id: -1 })
      .lean();

    result.push({
      watchlist_id: entry._id.toString(),
      stock: {
        id: entry.stock_id._id.toString(),
        symbol: entry.stock_id.symbol,
        company_name: entry.stock_id.company_name,
        exchange_code: entry.stock_id.exchange_code
      },
      latest_price: latestPrice ? {
        close_price: latestPrice.close_price,
        price_change: latestPrice.price_change || 0,
        price_change_percent: latestPrice.price_change_percent || 0,
        volume: latestPrice.volume
      } : null,
      created_at: entry.created_at
    });
  }

  return result;
};

const addStockToWatchlist = async (userId, symbol) => {
  const stock = await DimStock.findOne({ symbol: symbol.toUpperCase() });
  if (!stock) {
    const error = new Error('Stock symbol not found');
    error.statusCode = 404;
    throw error;
  }

  const existingEntry = await watchlistsRepository.findWatchlistEntry(userId, stock._id);
  if (existingEntry) {
    const error = new Error('Stock is already in your watchlist');
    error.statusCode = 400;
    throw error;
  }

  const currentCount = await watchlistsRepository.countUserWatchlist(userId);
  if (currentCount >= 5) {
    const error = new Error('Watchlist limit exceeded (Maximum 5 stocks allowed)');
    error.statusCode = 400;
    throw error;
  }

  const newEntry = await watchlistsRepository.createWatchlistEntry(userId, stock._id);

  return {
    watchlist_id: newEntry._id.toString(),
    symbol: stock.symbol,
    created_at: newEntry.created_at
  };
};

const removeStockFromWatchlist = async (userId, symbol) => {
  const stock = await DimStock.findOne({ symbol: symbol.toUpperCase() });
  if (!stock) {
    const error = new Error('Stock symbol not found');
    error.statusCode = 404;
    throw error;
  }

  const existingEntry = await watchlistsRepository.findWatchlistEntry(userId, stock._id);
  if (!existingEntry) {
    const error = new Error('Stock not found in your watchlist');
    error.statusCode = 404;
    throw error;
  }

  await watchlistsRepository.deleteWatchlistEntry(userId, stock._id);
  return true;
};

module.exports = {
  getUserWatchlist,
  addStockToWatchlist,
  removeStockFromWatchlist
};
