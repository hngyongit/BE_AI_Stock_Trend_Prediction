const stocksRepository = require('./stocks.repository');
const DimMarket = require('../../database/models/dim-market.model');
const DimStock = require('../../database/models/dim-stock.model');

const formatTimeIdToDateString = (timeId) => {
  const s = String(timeId);
  if (s.length !== 8) return s;
  return `${s.substring(0, 4)}-${s.substring(4, 6)}-${s.substring(6, 8)}`;
};

const getStocksList = async ({ keyword, market, page = 1, limit = 10 }) => {
  const pageNum = Number(page);
  const limitNum = Number(limit);

  const { items, totalItems } = await stocksRepository.findStocksAndCount({
    keyword,
    market,
    page: pageNum,
    limit: limitNum
  });

  const formattedItems = items.map(stock => ({
    id: stock._id.toString(),
    symbol: stock.symbol,
    company_name: stock.company_name,
    market_code: stock.market_id ? stock.market_id.code : '',
    status: stock.status
  }));

  const totalPages = Math.ceil(totalItems / limitNum);

  return {
    items: formattedItems,
    pagination: {
      page: pageNum,
      limit: limitNum,
      total_items: totalItems,
      total_pages: totalPages || 1
    }
  };
};

const getStockDetail = async (symbol) => {
  const stock = await stocksRepository.findStockBySymbol(symbol);
  if (!stock) {
    const error = new Error('Stock symbol not found');
    error.statusCode = 404;
    throw error;
  }

  const latestPrice = await stocksRepository.findLatestPriceForStock(stock._id);

  const result = {
    id: stock._id.toString(),
    symbol: stock.symbol,
    company_name: stock.company_name,
    market_code: stock.market_id ? stock.market_id.code : '',
    status: stock.status,
    listed_date: stock.listed_date || null,
    latest_price: null
  };

  if (latestPrice) {
    const { _id, stock_id, market_id, industry_id, data_source_id, __v, ...priceData } = latestPrice;
    result.latest_price = {
      ...priceData,
      price_change: priceData.price_change || 0,
      price_change_percent: priceData.price_change_percent || 0,
      market_cap: priceData.market_cap || 0
    };
  }

  return result;
};

const getStockChart = async (symbol, range = '1m') => {
  const stock = await stocksRepository.findStockBySymbol(symbol);
  if (!stock) {
    const error = new Error('Stock symbol not found');
    error.statusCode = 404;
    throw error;
  }

  const rangeMap = {
    '7d': 7,
    '1m': 30,
    '3m': 90,
    '6m': 180,
    '1y': 365,
    'all': null
  };

  const limitNum = rangeMap[range.toLowerCase()] !== undefined ? rangeMap[range.toLowerCase()] : 30;

  const prices = await stocksRepository.findPricesForStock(stock._id, limitNum);

  return prices.map(p => ({
    time: formatTimeIdToDateString(p.time_id),
    open: p.open_price,
    high: p.high_price,
    low: p.low_price,
    close: p.close_price,
    volume: p.volume
  }));
};

const createStockMaster = async (data) => {
  const symbolUpper = data.symbol.toUpperCase();
  const existingStock = await DimStock.findOne({ symbol: symbolUpper });
  if (existingStock) {
    const error = new Error('Stock symbol already exists');
    error.statusCode = 400;
    throw error;
  }

  const market = await DimMarket.findById(data.market_id);
  if (!market) {
    const error = new Error('Market not found');
    error.statusCode = 400;
    throw error;
  }

  const stock = await DimStock.create({
    market_id: market._id,
    industry_id: data.industry_id || undefined,
    symbol: symbolUpper,
    company_name: data.company_name,
    status: data.status || 'ACTIVE',
    listed_date: data.listed_date ? new Date(data.listed_date) : undefined
  });

  return {
    id: stock._id.toString(),
    symbol: stock.symbol,
    company_name: stock.company_name,
    market_id: stock.market_id.toString(),
    market_code: market.code,
    status: stock.status
  };
};

const updateStockMaster = async (id, data) => {
  const stock = await DimStock.findById(id);
  if (!stock) {
    const error = new Error('Stock not found');
    error.statusCode = 404;
    throw error;
  }

  if (data.company_name !== undefined) stock.company_name = data.company_name;
  if (data.status !== undefined) stock.status = data.status;
  if (data.listed_date !== undefined) stock.listed_date = new Date(data.listed_date);
  if (data.industry_id !== undefined) stock.industry_id = data.industry_id || null;

  let market;
  if (data.market_id !== undefined) {
    market = await DimMarket.findById(data.market_id);
    if (!market) {
      const error = new Error('Market not found');
      error.statusCode = 400;
      throw error;
    }
    stock.market_id = market._id;
  } else {
    market = await DimMarket.findById(stock.market_id);
  }

  await stock.save();

  return {
    id: stock._id.toString(),
    symbol: stock.symbol,
    company_name: stock.company_name,
    market_id: stock.market_id.toString(),
    market_code: market ? market.code : '',
    status: stock.status
  };
};

module.exports = {
  getStocksList,
  getStockDetail,
  getStockChart,
  createStockMaster,
  updateStockMaster
};
