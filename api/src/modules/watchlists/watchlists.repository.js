const Watchlist = require('../../database/models/watchlist.model');
const FactMarketPrice = require('../../database/models/fact-market-price.model');

const findUserWatchlist = async (userId) => {
  return Watchlist.find({ user_id: userId })
    .populate({
      path: 'stock_id',
      select: '_id symbol company_name market_id status',
      populate: {
        path: 'market_id',
        select: 'code'
      }
    })
    .lean();
};

const countUserWatchlist = async (userId) => {
  return Watchlist.countDocuments({ user_id: userId });
};

const findWatchlistEntry = async (userId, stockId) => {
  return Watchlist.findOne({ user_id: userId, stock_id: stockId }).lean();
};

const createWatchlistEntry = async (userId, stockId) => {
  return Watchlist.create({ user_id: userId, stock_id: stockId });
};

const deleteWatchlistEntry = async (userId, stockId) => {
  return Watchlist.deleteOne({ user_id: userId, stock_id: stockId });
};

module.exports = {
  findUserWatchlist,
  countUserWatchlist,
  findWatchlistEntry,
  createWatchlistEntry,
  deleteWatchlistEntry
};
