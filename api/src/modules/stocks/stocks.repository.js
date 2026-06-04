const DimStock = require('../../database/models/dim-stock.model');
const FactMarketPrice = require('../../database/models/fact-market-price.model');

const findStocksAndCount = async ({ keyword, market, page = 1, limit = 10 }) => {
  const query = {};

  if (keyword) {
    query.$or = [
      { symbol: { $regex: keyword, $options: 'i' } },
      { company_name: { $regex: keyword, $options: 'i' } }
    ];
  }

  if (market) {
    const DimMarket = require('../../database/models/dim-market.model');
    const foundMarket = await DimMarket.findOne({ code: market.toUpperCase() });
    if (foundMarket) {
      query.market_id = foundMarket._id;
    } else {
      return { items: [], totalItems: 0 };
    }
  }

  const skip = (page - 1) * limit;

  const [items, totalItems] = await Promise.all([
    DimStock.find(query).populate('market_id').skip(skip).limit(limit).lean(),
    DimStock.countDocuments(query)
  ]);

  return { items, totalItems };
};

const findStockBySymbol = async (symbol) => {
  return DimStock.findOne({ symbol: symbol.toUpperCase() }).populate('market_id').lean();
};

const findLatestPriceForStock = async (stockId) => {
  return FactMarketPrice.findOne({ stock_id: stockId })
    .sort({ time_id: -1 })
    .lean();
};

const findPricesForStock = async (stockId, daysLimit) => {
  let query = { stock_id: stockId };

  let pricesQuery = FactMarketPrice.find(query).sort({ time_id: -1 });
  if (daysLimit) {
    pricesQuery = pricesQuery.limit(daysLimit);
  }

  const prices = await pricesQuery.lean();
  // Reverse to make it ascending (chronological) for the chart
  return prices.reverse();
};

module.exports = {
  findStocksAndCount,
  findStockBySymbol,
  findLatestPriceForStock,
  findPricesForStock
};
