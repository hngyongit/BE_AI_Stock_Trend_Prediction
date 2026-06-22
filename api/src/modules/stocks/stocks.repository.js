const DimStock = require('../../database/models/dim-stock.model');
const FactMarketPrice = require('../../database/models/fact-market-price.model');
const FactFinancialStatement = require('../../database/models/fact-financial-statement.model');
const FactMarketOverview = require('../../database/models/fact-market-overview.model');

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
  return DimStock.findOne({ symbol: symbol.toUpperCase() })
    .populate('market_id')
    .populate('industry_id')
    .lean();
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

const findFinancialStatementsForStock = async (stockId, limit = 6) => {
  const rows = await FactFinancialStatement.find({ stock_id: stockId })
    .populate('report_period_id')
    .populate('data_source_id')
    .lean();

  return rows
    .sort((a, b) => {
      const aPeriod = a.report_period_id || {};
      const bPeriod = b.report_period_id || {};
      const aYear = Number(aPeriod.fiscal_year || 0);
      const bYear = Number(bPeriod.fiscal_year || 0);
      if (aYear !== bYear) return bYear - aYear;
      return Number(bPeriod.fiscal_quarter || 0) - Number(aPeriod.fiscal_quarter || 0);
    })
    .slice(0, Number(limit) || 6);
};

const findLatestMarketOverviewForMarket = async (marketId, marketCode) => {
  const query = {};
  if (marketId) {
    query.market_id = marketId;
  }

  const normalizedCode = String(marketCode || '').toUpperCase();
  const preferredSymbols = normalizedCode === 'HOSE'
    ? ['VNINDEX', 'VN-INDEX', 'VN Index']
    : [];

  if (preferredSymbols.length > 0) {
    const preferred = await FactMarketOverview.findOne({
      ...query,
      symbol: { $in: preferredSymbols }
    })
      .sort({ time_id: -1 })
      .lean();

    if (preferred) {
      return preferred;
    }
  }

  return FactMarketOverview.findOne(query).sort({ time_id: -1 }).lean();
};

const findPeersByIndustry = async (industryId, excludedStockId, limit = 10) => {
  if (!industryId) return [];

  return DimStock.find({
    industry_id: industryId,
    _id: { $ne: excludedStockId },
    status: 'ACTIVE'
  })
    .populate('market_id')
    .populate('industry_id')
    .limit(Number(limit) || 10)
    .lean();
};

module.exports = {
  findStocksAndCount,
  findStockBySymbol,
  findLatestPriceForStock,
  findPricesForStock,
  findFinancialStatementsForStock,
  findLatestMarketOverviewForMarket,
  findPeersByIndustry
};
