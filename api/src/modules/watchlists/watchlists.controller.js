const watchlistsService = require('./watchlists.service');
const { success } = require('../../common/utils/response.util');

const getWatchlist = async (req, res, next) => {
  try {
    const userId = req.user._id || req.user.id;
    const userPlan = req.user.plan || 'FREE';
    const result = await watchlistsService.getUserWatchlist(userId, userPlan);
    return success(res, 'Get watchlist successfully', result);
  } catch (error) {
    next(error);
  }
};

const addWatchlist = async (req, res, next) => {
  try {
    const userId = req.user._id || req.user.id;
    const userPlan = req.user.plan || 'FREE';
    const { symbol } = req.body;
    const result = await watchlistsService.addStockToWatchlist(userId, symbol, userPlan);
    return success(res, 'Add stock to watchlist successfully', result, 201);
  } catch (error) {
    next(error);
  }
};

const removeWatchlist = async (req, res, next) => {
  try {
    const userId = req.user._id || req.user.id;
    const { symbol } = req.params;
    await watchlistsService.removeStockFromWatchlist(userId, symbol);
    return success(res, 'Remove stock from watchlist successfully');
  } catch (error) {
    next(error);
  }
};

const trimWatchlist = async (req, res, next) => {
  try {
    const userId = req.user._id || req.user.id;
    const userPlan = req.user.plan || 'FREE';
    const { keepStockIds } = req.body;
    const result = await watchlistsService.trimWatchlist(userId, keepStockIds, userPlan);
    return success(res, 'Trim watchlist successfully', result);
  } catch (error) {
    next(error);
  }
};

module.exports = {
  getWatchlist,
  addWatchlist,
  removeWatchlist,
  trimWatchlist
};
