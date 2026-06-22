const assert = require('assert');
const http = require('http');
const express = require('express');

const User = require('../src/database/models/user.model');
const { generateAccessToken } = require('../src/common/utils/jwt.util');
const watchlistsService = require('../src/modules/watchlists/watchlists.service');
const watchlistsRouter = require('../src/modules/watchlists/watchlists.routes');
const stocksRepository = require('../src/modules/stocks/stocks.repository');
const stocksService = require('../src/modules/stocks/stocks.service');
const errorMiddleware = require('../src/common/middlewares/error.middleware');

const tests = [];

const test = (name, fn) => {
  tests.push({ name, fn });
};

const oid = (value) => ({ toString: () => value });

const request = (server, path, headers = {}) => {
  const address = server.address();
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: address.port,
        path,
        method: 'GET',
        headers
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => {
          body += chunk;
        });
        res.on('end', () => {
          resolve({
            status: res.statusCode,
            body,
            json: body ? JSON.parse(body) : null
          });
        });
      }
    );
    req.on('error', reject);
    req.end();
  });
};

const withServer = async (app, fn) => {
  const server = await new Promise((resolve) => {
    const running = app.listen(0, () => resolve(running));
  });
  try {
    await fn(server);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
};

const withRepositoryStubs = async (stubs, fn) => {
  const originals = {};
  for (const [key, value] of Object.entries(stubs)) {
    originals[key] = stocksRepository[key];
    stocksRepository[key] = value;
  }
  try {
    await fn();
  } finally {
    for (const [key, value] of Object.entries(originals)) {
      stocksRepository[key] = value;
    }
  }
};

const buildStockFixture = () => ({
  stock: {
    _id: oid('stock-fpt'),
    symbol: 'FPT',
    company_name: 'CTCP FPT',
    status: 'ACTIVE',
    listed_date: new Date('2006-12-13T00:00:00.000Z'),
    market_id: {
      _id: oid('market-hose'),
      code: 'HOSE',
      name: 'Ho Chi Minh Stock Exchange'
    },
    industry_id: {
      _id: oid('industry-tech'),
      industry_name: 'Technology',
      sector_name: 'Information Technology'
    }
  },
  peer: {
    _id: oid('stock-cmg'),
    symbol: 'CMG',
    company_name: 'CTCP Tập đoàn Công nghệ CMC',
    market_id: {
      _id: oid('market-hose'),
      code: 'HOSE'
    },
    industry_id: {
      _id: oid('industry-tech'),
      industry_name: 'Technology',
      sector_name: 'Information Technology'
    }
  },
  price: {
    time_id: 20260619,
    open_price: 71600,
    high_price: 71800,
    low_price: 70800,
    close_price: 71500,
    volume: 14295100,
    foreign_buy: 1915100,
    foreign_sell: 71500,
    foreign_net: 1843600,
    market_cap: 121801,
    eps: 6010,
    pe: 1.73,
    forward_pe: 10.49,
    bvps: 23553,
    pb: 3.04,
    beta: 0.88,
    roe: 5.93,
    ros: 19.85,
    roaa: 3.17,
    price_change: 500,
    price_change_percent: 0.7,
    crawled_at: new Date('2026-06-19T10:00:00.000Z')
  },
  peerPrice: {
    time_id: 20260619,
    open_price: 52000,
    high_price: 53000,
    low_price: 51000,
    close_price: 52500,
    volume: 900000,
    market_cap: 12000,
    pe: 13.2,
    pb: 2.1,
    roe: 12.4
  },
  prices: [
    { time_id: 20260601, open_price: 69000, high_price: 70000, low_price: 68000, close_price: 69000, volume: 1000000 },
    { time_id: 20260619, open_price: 71600, high_price: 71800, low_price: 70800, close_price: 71500, volume: 14295100 }
  ],
  peerPrices: [
    { time_id: 20260601, open_price: 50000, high_price: 50500, low_price: 49500, close_price: 50000, volume: 300000 },
    { time_id: 20260619, open_price: 52000, high_price: 53000, low_price: 51000, close_price: 52500, volume: 900000 }
  ],
  financial: {
    report_period_id: {
      fiscal_year: 2026,
      fiscal_quarter: 1,
      period_name: 'Q1/2026'
    },
    data_source_id: {
      financial_data_url: 'https://example.com/fpt-financials'
    },
    net_revenue: 123456,
    gross_profit: 45678,
    net_profit_from_operating_activities: 34567,
    profit_before_tax: 23456,
    profit_after_tax: 20000,
    parent_company_profit: 19000,
    eps: 1234,
    total_assets: 500000,
    liabilities: 200000,
    equity: 300000,
    current_assets: 250000,
    current_liabilities: 100000,
    roe: 15.5,
    crawled_at: new Date('2026-06-20T00:00:00.000Z')
  },
  overview: {
    symbol: 'VNINDEX',
    display_symbol: 'VNINDEX',
    time_id: 20260619,
    close_index: 1300.12,
    open_index: 1305,
    high_index: 1310,
    low_index: 1295,
    change_value: -10.5,
    change_percent: -0.8,
    total_volume: 123456789,
    total_value: 123456,
    foreign_buy: 100,
    foreign_sell: 200,
    foreign_net: -100,
    source: 'mongo:test'
  }
});

test('/api/watchlists không có token trả 401, token hợp lệ trả 200', async () => {
  const originalGetUserWatchlist = watchlistsService.getUserWatchlist;
  const originalFindById = User.findById;

  watchlistsService.getUserWatchlist = async () => ({
    items: [],
    limit: 5,
    currentCount: 0,
    overLimit: false
  });
  User.findById = () => ({
    populate: async () => ({
      _id: oid('507f1f77bcf86cd799439011'),
      id: '507f1f77bcf86cd799439011',
      email: 'user@example.com',
      role_id: { name: 'USER' },
      status: 'ACTIVE',
      plan: 'FREE'
    })
  });

  const app = express();
  app.use(express.json());
  app.use('/api/watchlists', watchlistsRouter);
  app.use(errorMiddleware);

  try {
    await withServer(app, async (server) => {
      const noToken = await request(server, '/api/watchlists');
      assert.strictEqual(noToken.status, 401);

      const token = generateAccessToken({
        _id: '507f1f77bcf86cd799439011',
        email: 'user@example.com',
        role: 'USER',
        plan: 'FREE'
      });
      const ok = await request(server, '/api/watchlists', {
        Authorization: `Bearer ${token}`
      });
      assert.strictEqual(ok.status, 200);
      assert.strictEqual(ok.json.success, true);
      assert.deepStrictEqual(ok.json.data.items, []);
    });
  } finally {
    watchlistsService.getUserWatchlist = originalGetUserWatchlist;
    User.findById = originalFindById;
  }
});

test('stocksService.getStockAnalysisData trả contract đầy đủ cho analyse', async () => {
  const fixture = buildStockFixture();

  await withRepositoryStubs({
    findStockBySymbol: async () => fixture.stock,
    findLatestPriceForStock: async (stockId) => (
      stockId.toString() === 'stock-cmg' ? fixture.peerPrice : fixture.price
    ),
    findPricesForStock: async (stockId) => (
      stockId.toString() === 'stock-cmg' ? fixture.peerPrices : fixture.prices
    ),
    findFinancialStatementsForStock: async (stockId) => (
      stockId.toString() === 'stock-cmg'
        ? [{ ...fixture.financial, profit_after_tax: 8000, net_revenue: 50000 }]
        : [fixture.financial]
    ),
    findLatestMarketOverviewForMarket: async () => fixture.overview,
    findPeersByIndustry: async () => [fixture.peer]
  }, async () => {
    const result = await stocksService.getStockAnalysisData('FPT', {
      quarters: 6,
      chartRange: '3m',
      includePeers: true,
      includeMarketContext: true
    });

    assert.strictEqual(result.symbol, 'FPT');
    assert.strictEqual(result.exchange, 'HOSE');
    assert.strictEqual(result.latestMarket.close_price, 71500);
    assert.strictEqual(result.priceHistory.length, 2);
    assert.strictEqual(result.financials.periods.length, 1);
    assert.strictEqual(result.financials.periods[0].revenue, 123456);
    assert.strictEqual(result.financialBalance.total_assets, 500000);
    assert.strictEqual(result.hoseMarketContext.vnindex, 1300.12);
    assert.strictEqual(result.industryPeerContext.peers[0].symbol, 'CMG');
    assert.strictEqual(result.dataQuality.financialsLoaded, true);
    assert.strictEqual(result.dataQuality.priceHistoryPoints, 2);
    assert.strictEqual(result.dataQuality.units.percent_fields, 'percentage_points');
    assert.strictEqual(Object.prototype.hasOwnProperty.call(result.financials.periods[0], 'net_revenue'), false);
  });
});

test('stocksService.getStockDetail bổ sung field backward-compatible cho analyse hiện tại', async () => {
  const fixture = buildStockFixture();

  await withRepositoryStubs({
    findStockBySymbol: async () => fixture.stock,
    findLatestPriceForStock: async () => fixture.price,
    findPricesForStock: async () => fixture.prices,
    findFinancialStatementsForStock: async () => [fixture.financial],
    findLatestMarketOverviewForMarket: async () => fixture.overview,
    findPeersByIndustry: async () => []
  }, async () => {
    const result = await stocksService.getStockDetail('FPT');

    assert.strictEqual(result.symbol, 'FPT');
    assert.strictEqual(Array.isArray(result.financials), true);
    assert.strictEqual(result.financials[0].period, 'Q1/2026');
    assert.strictEqual(result.market_overview.vnindex, 1300.12);
    assert.strictEqual(result.dataQuality.financialsLoaded, true);
  });
});

test('stocksService.getStockAnalysisData vẫn trả dataQuality khi thiếu BCTC/market/peer', async () => {
  const fixture = buildStockFixture();

  await withRepositoryStubs({
    findStockBySymbol: async () => fixture.stock,
    findLatestPriceForStock: async () => fixture.price,
    findPricesForStock: async () => [],
    findFinancialStatementsForStock: async () => [],
    findLatestMarketOverviewForMarket: async () => null,
    findPeersByIndustry: async () => []
  }, async () => {
    const result = await stocksService.getStockAnalysisData('FPT', {
      quarters: 6,
      chartRange: '3m',
      includePeers: true,
      includeMarketContext: true
    });

    assert.strictEqual(result.financials.periods.length, 0);
    assert.strictEqual(result.dataQuality.financialsLoaded, false);
    assert.ok(result.dataQuality.missingFields.includes('financials.periods'));
    assert.ok(result.dataQuality.warnings.some((warning) => warning.includes('BCTC')));
  });
});

(async () => {
  for (const { name, fn } of tests) {
    await fn();
    console.log(`✓ ${name}`);
  }
  console.log(`All ${tests.length} api analyse contract tests passed.`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
