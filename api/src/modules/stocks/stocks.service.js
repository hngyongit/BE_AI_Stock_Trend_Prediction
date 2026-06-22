const stocksRepository = require('./stocks.repository');
const DimMarket = require('../../database/models/dim-market.model');
const DimStock = require('../../database/models/dim-stock.model');

const RANGE_TO_DAYS = {
  '7d': 7,
  '1m': 30,
  '3m': 90,
  '6m': 180,
  '1y': 365,
  all: null
};

const formatTimeIdToDateString = (timeId) => {
  const s = String(timeId);
  if (s.length !== 8) return s;
  return `${s.substring(0, 4)}-${s.substring(4, 6)}-${s.substring(6, 8)}`;
};

const toNumberOrNull = (value) => (
  typeof value === 'number' && Number.isFinite(value) ? value : null
);

const getRangeLimit = (range = '1m') => {
  const normalized = String(range || '1m').toLowerCase();
  return Object.prototype.hasOwnProperty.call(RANGE_TO_DAYS, normalized)
    ? RANGE_TO_DAYS[normalized]
    : RANGE_TO_DAYS['1m'];
};

const parseBooleanOption = (value, fallback = true) => {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'boolean') return value;
  return String(value).toLowerCase() === 'true';
};

const normalizeLatestMarket = (latestPrice) => {
  if (!latestPrice) return null;

  return {
    time_id: latestPrice.time_id ?? null,
    open_price: toNumberOrNull(latestPrice.open_price),
    high_price: toNumberOrNull(latestPrice.high_price),
    low_price: toNumberOrNull(latestPrice.low_price),
    close_price: toNumberOrNull(latestPrice.close_price),
    volume: toNumberOrNull(latestPrice.volume),
    bid_volume: toNumberOrNull(latestPrice.bid_volume),
    ask_volume: toNumberOrNull(latestPrice.ask_volume),
    foreign_buy: toNumberOrNull(latestPrice.foreign_buy),
    foreign_sell: toNumberOrNull(latestPrice.foreign_sell),
    foreign_net: toNumberOrNull(latestPrice.foreign_net),
    market_cap: toNumberOrNull(latestPrice.market_cap),
    eps: toNumberOrNull(latestPrice.eps),
    pe: toNumberOrNull(latestPrice.pe),
    forward_pe: toNumberOrNull(latestPrice.forward_pe),
    bvps: toNumberOrNull(latestPrice.bvps),
    pb: toNumberOrNull(latestPrice.pb),
    beta: toNumberOrNull(latestPrice.beta),
    roe: toNumberOrNull(latestPrice.roe),
    ros: toNumberOrNull(latestPrice.ros),
    roaa: toNumberOrNull(latestPrice.roaa),
    price_change: toNumberOrNull(latestPrice.price_change) ?? 0,
    price_change_percent: toNumberOrNull(latestPrice.price_change_percent) ?? 0,
    crawled_at: latestPrice.crawled_at || latestPrice.created_at || null
  };
};

const normalizePricePoint = (price) => ({
  time_id: price.time_id ?? null,
  time: formatTimeIdToDateString(price.time_id),
  open_price: toNumberOrNull(price.open_price),
  high_price: toNumberOrNull(price.high_price),
  low_price: toNumberOrNull(price.low_price),
  close_price: toNumberOrNull(price.close_price),
  volume: toNumberOrNull(price.volume),
  open: toNumberOrNull(price.open_price),
  high: toNumberOrNull(price.high_price),
  low: toNumberOrNull(price.low_price),
  close: toNumberOrNull(price.close_price)
});

const normalizeFinancialPeriod = (statement) => {
  const period = statement.report_period_id || {};
  const source = statement.data_source_id || {};
  const year = period.fiscal_year ?? null;
  const quarter = period.fiscal_quarter ?? null;

  return {
    period: period.period_name || (year && quarter ? `Q${quarter}/${year}` : null),
    year,
    quarter,
    revenue: toNumberOrNull(statement.net_revenue),
    gross_profit: toNumberOrNull(statement.gross_profit),
    operating_profit: toNumberOrNull(statement.net_profit_from_operating_activities),
    profit_before_tax: toNumberOrNull(statement.profit_before_tax),
    profit_after_tax: toNumberOrNull(statement.profit_after_tax),
    parent_profit: toNumberOrNull(statement.parent_company_profit),
    eps: toNumberOrNull(statement.eps),
    total_assets: toNumberOrNull(statement.total_assets),
    total_liabilities: toNumberOrNull(statement.liabilities),
    equity: toNumberOrNull(statement.equity),
    current_assets: toNumberOrNull(statement.current_assets),
    current_liabilities: toNumberOrNull(statement.current_liabilities),
    cash: null,
    debt: null,
    operating_cash_flow: null,
    free_cash_flow: null,
    net_interest_income: toNumberOrNull(statement.net_interest_income),
    operating_expense: toNumberOrNull(statement.operating_expense),
    total_operating_income: toNumberOrNull(statement.total_operating_income),
    customer_loans: toNumberOrNull(statement.customer_loans),
    customer_deposits: toNumberOrNull(statement.customer_deposits),
    retained_earnings: toNumberOrNull(statement.retained_earnings),
    pe: toNumberOrNull(statement.pe),
    forward_pe: toNumberOrNull(statement.forward_pe),
    bvps: toNumberOrNull(statement.bvps),
    pb: toNumberOrNull(statement.pb),
    beta: toNumberOrNull(statement.beta),
    ros: toNumberOrNull(statement.ros),
    roe: toNumberOrNull(statement.roe),
    roaa: toNumberOrNull(statement.roaa),
    source: source.financial_data_url ? 'mongo:dimStockDataSources' : 'mongo:factFinancialStatements',
    source_url: source.financial_data_url || null,
    updated_at: statement.crawled_at || statement.created_at || null
  };
};

const buildFinancials = (statements, requestedLimit) => {
  const periods = (statements || []).map(normalizeFinancialPeriod);
  return {
    periods,
    source: periods.length > 0 ? 'mongo:factFinancialStatements' : null,
    updated_at: periods[0]?.updated_at || null,
    requested_periods: requestedLimit,
    units: {
      money_fields: 'Cần kiểm tra thêm: source/crawler chưa ghi rõ đơn vị tiền tệ trong model.',
      eps: 'VND/cổ phiếu nếu dữ liệu nguồn lưu đúng chuẩn.',
      percent_fields: 'percentage_points'
    }
  };
};

const buildFinancialBalance = (financials) => {
  const latest = financials?.periods?.[0];
  if (!latest) return {};

  return {
    period: latest.period,
    year: latest.year,
    quarter: latest.quarter,
    total_assets: latest.total_assets,
    total_liabilities: latest.total_liabilities,
    equity: latest.equity,
    current_assets: latest.current_assets,
    current_liabilities: latest.current_liabilities,
    retained_earnings: latest.retained_earnings,
    customer_loans: latest.customer_loans,
    customer_deposits: latest.customer_deposits,
    updated_at: latest.updated_at
  };
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const buildMarketRegime = (changePercent) => {
  const pct = toNumberOrNull(changePercent);
  if (pct == null) {
    return { regime: 'neutral', regime_score: null };
  }
  if (pct >= 0.5) {
    return { regime: 'risk_on', regime_score: clamp(Math.round(60 + pct * 8), 0, 100) };
  }
  if (pct <= -0.5) {
    return { regime: 'risk_off', regime_score: clamp(Math.round(40 + pct * 8), 0, 100) };
  }
  return { regime: 'neutral', regime_score: clamp(Math.round(50 + pct * 8), 0, 100) };
};

const normalizeMarketContext = (marketOverview) => {
  if (!marketOverview) return {};

  const regime = buildMarketRegime(marketOverview.change_percent);
  return {
    index_symbol: marketOverview.symbol || null,
    display_symbol: marketOverview.display_symbol || marketOverview.symbol || null,
    vnindex: toNumberOrNull(marketOverview.close_index),
    open_index: toNumberOrNull(marketOverview.open_index),
    high_index: toNumberOrNull(marketOverview.high_index),
    low_index: toNumberOrNull(marketOverview.low_index),
    change: toNumberOrNull(marketOverview.change_value),
    change_percent: toNumberOrNull(marketOverview.change_percent),
    total_volume: toNumberOrNull(marketOverview.total_volume),
    total_value: toNumberOrNull(marketOverview.total_value),
    foreign_buy: toNumberOrNull(marketOverview.foreign_buy),
    foreign_sell: toNumberOrNull(marketOverview.foreign_sell),
    foreign_net: toNumberOrNull(marketOverview.foreign_net),
    breadth: {
      advancers: null,
      decliners: null,
      unchanged: null
    },
    regime: regime.regime,
    regime_score: regime.regime_score,
    time_id: marketOverview.time_id ?? null,
    updated_at: marketOverview.last_trading_time || marketOverview.created_at || null,
    source: marketOverview.source || 'mongo:factMarketOverviews'
  };
};

const calculateMomentumPct = (prices) => {
  if (!Array.isArray(prices) || prices.length < 2) return null;
  const first = prices[0]?.close_price;
  const last = prices[prices.length - 1]?.close_price;
  if (typeof first !== 'number' || typeof last !== 'number' || first === 0) return null;
  return Number((((last - first) / first) * 100).toFixed(2));
};

const normalizeIndustry = (stock) => {
  const industry = stock.industry_id;
  if (!industry) {
    return {
      sector: null,
      industry: null,
      source: null
    };
  }

  return {
    sector: industry.sector_name || null,
    industry: industry.industry_name || null,
    source: 'mongo:dimIndustries'
  };
};

const normalizePeer = async (peer) => {
  const [latestPrice, latestFinancialRows, momentumPrices] = await Promise.all([
    stocksRepository.findLatestPriceForStock(peer._id),
    stocksRepository.findFinancialStatementsForStock(peer._id, 1),
    stocksRepository.findPricesForStock(peer._id, 30)
  ]);
  const latestFinancial = latestFinancialRows?.[0] ? normalizeFinancialPeriod(latestFinancialRows[0]) : {};
  const latestMarket = normalizeLatestMarket(latestPrice) || {};

  return {
    symbol: peer.symbol,
    company: peer.company_name,
    exchange: peer.market_id?.code || null,
    close_price: latestMarket.close_price ?? null,
    pe: latestMarket.pe ?? latestFinancial.pe ?? null,
    pb: latestMarket.pb ?? latestFinancial.pb ?? null,
    roe: latestMarket.roe ?? latestFinancial.roe ?? null,
    market_cap: latestMarket.market_cap ?? null,
    profit_after_tax: latestFinancial.profit_after_tax ?? null,
    revenue: latestFinancial.revenue ?? null,
    momentum_1m: calculateMomentumPct(momentumPrices)
  };
};

const buildSameIndustryRecommendation = (peers) => {
  if (!Array.isArray(peers) || peers.length === 0) return {};

  const candidates = [...peers]
    .sort((a, b) => {
      const aScore = (toNumberOrNull(a.roe) ?? -Infinity) + (toNumberOrNull(a.momentum_1m) ?? 0);
      const bScore = (toNumberOrNull(b.roe) ?? -Infinity) + (toNumberOrNull(b.momentum_1m) ?? 0);
      return bScore - aScore;
    })
    .slice(0, 5);

  return {
    candidates,
    method: 'Sắp xếp kỹ thuật từ dữ liệu peer có sẵn; không phải khuyến nghị mua/bán.',
    source: 'mongo:dimStocks,factMarketPrices,factFinancialStatements'
  };
};

const buildDataQuality = ({
  latestMarket,
  priceHistory,
  financials,
  marketContext,
  peers,
  stock
}) => {
  const missingFields = [];
  const warnings = [];

  if (!latestMarket) missingFields.push('latestMarket');
  if (!Array.isArray(priceHistory) || priceHistory.length === 0) missingFields.push('priceHistory');
  if (!financials?.periods?.length) {
    missingFields.push('financials.periods');
    warnings.push('Không tìm thấy BCTC trong factFinancialStatements cho mã này.');
  }
  if (!marketContext || Object.keys(marketContext).length === 0) {
    missingFields.push('hoseMarketContext');
    warnings.push('Không tìm thấy VNINDEX/market overview trong factMarketOverviews.');
  }
  if (!stock.industry_id) {
    missingFields.push('industry');
    warnings.push('Stock chưa gắn industry_id nên không thể dựng peer context đầy đủ.');
  }
  if (!Array.isArray(peers) || peers.length === 0) {
    missingFields.push('industryPeerContext.peers');
  }

  warnings.push('Đơn vị tiền tệ/market_cap cần kiểm tra thêm vì model hiện chưa lưu metadata đơn vị.');

  return {
    financialsLoaded: Boolean(financials?.periods?.length),
    financialPeriodsCount: financials?.periods?.length || 0,
    priceHistoryPoints: Array.isArray(priceHistory) ? priceHistory.length : 0,
    marketContextLoaded: Boolean(marketContext && Object.keys(marketContext).length > 0),
    peerContextLoaded: Array.isArray(peers) && peers.length > 0,
    missingFields,
    warnings,
    units: {
      price: 'VND',
      volume: 'shares',
      percent_fields: 'percentage_points',
      financial_statement_money_fields: 'Cần kiểm tra thêm',
      market_cap: 'Cần kiểm tra thêm'
    }
  };
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
  const supplemental = await buildAnalysisDataForStock(stock, {
    quarters: 6,
    chartRange: '3m',
    includePeers: true,
    includeMarketContext: true
  });

  const result = {
    id: stock._id.toString(),
    symbol: stock.symbol,
    company_name: stock.company_name,
    market_code: stock.market_id ? stock.market_id.code : '',
    industry: normalizeIndustry(stock),
    status: stock.status,
    listed_date: stock.listed_date || null,
    latest_price: null,
    latestMarket: null,
    latest_market: null,
    financials: supplemental.financials.periods,
    financials_summary: supplemental.financials,
    financialBalance: supplemental.financialBalance,
    financial_balance: supplemental.financialBalance,
    market_overview: supplemental.hoseMarketContext,
    hoseMarketContext: supplemental.hoseMarketContext,
    marketGeneralContext: supplemental.marketGeneralContext,
    market_general_context: supplemental.marketGeneralContext,
    industryPeerContext: supplemental.industryPeerContext,
    industry_peer_context: supplemental.industryPeerContext,
    sameIndustryRecommendation: supplemental.sameIndustryRecommendation,
    same_industry_recommendation: supplemental.sameIndustryRecommendation,
    dataQuality: supplemental.dataQuality
  };

  if (latestPrice) {
    const { _id, stock_id, market_id, industry_id, data_source_id, __v, ...priceData } = latestPrice;
    result.latest_price = {
      ...priceData,
      price_change: priceData.price_change || 0,
      price_change_percent: priceData.price_change_percent || 0,
      market_cap: priceData.market_cap || 0
    };
    result.latestMarket = normalizeLatestMarket(latestPrice);
    result.latest_market = result.latestMarket;
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

  const limitNum = getRangeLimit(range);

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

const buildAnalysisDataForStock = async (
  stock,
  {
    quarters = 6,
    chartRange = '3m',
    includePeers = true,
    includeMarketContext = true
  } = {}
) => {
  const marketCode = stock.market_id?.code || '';
  const marketId = stock.market_id?._id || stock.market_id || null;
  const industryId = stock.industry_id?._id || stock.industry_id || null;
  const normalizedQuarters = Math.max(1, Math.min(Number(quarters) || 6, 12));
  const shouldIncludePeers = parseBooleanOption(includePeers, true);
  const shouldIncludeMarketContext = parseBooleanOption(includeMarketContext, true);

  const [
    latestPrice,
    priceRows,
    financialRows,
    marketOverview,
    peerStocks
  ] = await Promise.all([
    stocksRepository.findLatestPriceForStock(stock._id),
    stocksRepository.findPricesForStock(stock._id, getRangeLimit(chartRange)),
    stocksRepository.findFinancialStatementsForStock(stock._id, normalizedQuarters),
    shouldIncludeMarketContext
      ? stocksRepository.findLatestMarketOverviewForMarket(marketId, marketCode)
      : Promise.resolve(null),
    shouldIncludePeers
      ? stocksRepository.findPeersByIndustry(industryId, stock._id, 10)
      : Promise.resolve([])
  ]);

  const latestMarket = normalizeLatestMarket(latestPrice);
  const priceHistory = (priceRows || []).map(normalizePricePoint);
  const financials = buildFinancials(financialRows, normalizedQuarters);
  const financialBalance = buildFinancialBalance(financials);
  const hoseMarketContext = normalizeMarketContext(marketOverview);
  const peers = shouldIncludePeers
    ? await Promise.all((peerStocks || []).map(normalizePeer))
    : [];
  const industryPeerContext = {
    industry: normalizeIndustry(stock),
    peers,
    source: peers.length > 0
      ? 'mongo:dimStocks,factMarketPrices,factFinancialStatements'
      : null
  };
  const sameIndustryRecommendation = buildSameIndustryRecommendation(peers);
  const marketGeneralContext = {
    exchange: marketCode || null,
    primary_index: hoseMarketContext || {},
    source: Object.keys(hoseMarketContext || {}).length > 0 ? hoseMarketContext.source : null
  };
  const dataQuality = buildDataQuality({
    latestMarket,
    priceHistory,
    financials,
    marketContext: hoseMarketContext,
    peers,
    stock
  });

  return {
    symbol: stock.symbol,
    exchange: marketCode,
    company: stock.company_name,
    latestMarket,
    latest_market: latestMarket,
    latest_price: latestMarket,
    priceHistory,
    price_history: priceHistory,
    financials,
    financialBalance,
    financial_balance: financialBalance,
    hoseMarketContext,
    market_overview: hoseMarketContext,
    industryPeerContext,
    industry_peer_context: industryPeerContext,
    marketGeneralContext,
    market_general_context: marketGeneralContext,
    sameIndustryRecommendation,
    same_industry_recommendation: sameIndustryRecommendation,
    dataQuality
  };
};

const getStockAnalysisData = async (symbol, options = {}) => {
  const stock = await stocksRepository.findStockBySymbol(symbol);
  if (!stock) {
    const error = new Error('Stock symbol not found');
    error.statusCode = 404;
    throw error;
  }

  const payload = await buildAnalysisDataForStock(stock, options);
  return {
    id: stock._id.toString(),
    symbol: payload.symbol,
    exchange: payload.exchange,
    company: payload.company,
    market_code: payload.exchange,
    industry: payload.industryPeerContext.industry,
    latestMarket: payload.latestMarket,
    latest_market: payload.latest_market,
    latest_price: payload.latest_price,
    priceHistory: payload.priceHistory,
    price_history: payload.price_history,
    financials: payload.financials,
    financialBalance: payload.financialBalance,
    financial_balance: payload.financial_balance,
    hoseMarketContext: payload.hoseMarketContext,
    market_overview: payload.market_overview,
    industryPeerContext: payload.industryPeerContext,
    industry_peer_context: payload.industry_peer_context,
    marketGeneralContext: payload.marketGeneralContext,
    market_general_context: payload.market_general_context,
    sameIndustryRecommendation: payload.sameIndustryRecommendation,
    same_industry_recommendation: payload.same_industry_recommendation,
    dataQuality: payload.dataQuality
  };
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
  getStockAnalysisData,
  createStockMaster,
  updateStockMaster
};
