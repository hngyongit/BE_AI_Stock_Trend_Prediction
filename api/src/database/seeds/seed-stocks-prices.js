const mongoose = require('mongoose');
const DimMarket = require('../models/dim-market.model');
const DimIndustry = require('../models/dim-industry.model');
const DimDataSource = require('../models/dim-data-source.model');
const DimStock = require('../models/dim-stock.model');
const FactMarketPrice = require('../models/fact-market-price.model');

const formatTimeId = (date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return Number(`${y}${m}${d}`);
};

const seedStocksAndPrices = async () => {
  try {
    // 1. Fetch pre-requisite dimension records
    const hose = await DimMarket.findOne({ code: 'HOSE' });
    if (!hose) throw new Error('HOSE market not found. Seed markets first.');

    const ssi = await DimDataSource.findOne({ name: 'ssi' });
    if (!ssi) throw new Error('ssi data source not found. Seed data sources first.');

    const tech = await DimIndustry.findOne({ industry_name: 'Technology' });
    const finance = await DimIndustry.findOne({ industry_name: 'Banking' });
    const consumer = await DimIndustry.findOne({ industry_name: 'Consumer Goods' });
    const steel = await DimIndustry.findOne({ industry_name: 'Steel' });

    const stocksToSeed = [
      { symbol: 'FPT', company_name: 'Công ty Cổ phần FPT', industry: tech, slug: 'FPT-ctcp-fpt', basePrice: 130000, vol: 2000000 },
      { symbol: 'HPG', company_name: 'Công ty Cổ phần Tập đoàn Hòa Phát', industry: steel, slug: 'HPG-ctcp-tap-doan-hoa-phat', basePrice: 28000, vol: 10000000 },
      { symbol: 'VNM', company_name: 'Công ty Cổ phần Sữa Việt Nam', industry: consumer, slug: 'VNM-ctcp-sua-viet-nam', basePrice: 68000, vol: 1500000 },
      { symbol: 'VIC', company_name: 'Tập đoàn Vingroup - Công ty CP', industry: consumer, slug: 'VIC-tap-doan-vingroup', basePrice: 42000, vol: 2500000 },
      { symbol: 'TCB', company_name: 'Ngân hàng TMCP Kỹ thương Việt Nam', industry: finance, slug: 'TCB-ngan-hang-tmcp-ky-thuong-viet-nam', basePrice: 48000, vol: 8000000 }
    ];

    // Clear existing stocks and prices
    await FactMarketPrice.deleteMany({});
    await DimStock.deleteMany({});
    console.log('[Seed] Cleared existing stocks and fact market prices.');

    for (const item of stocksToSeed) {
      // Create Stock
      const stock = await DimStock.create({
        market_id: hose._id,
        industry_id: item.industry?._id,
        symbol: item.symbol,
        company_name: item.company_name,
        exchange_code: 'HOSE',
        status: 'ACTIVE',
        listed_date: new Date('2006-12-13'),
        slug: item.slug
      });
      console.log(`[Seed] Created stock: ${item.symbol}`);

      // Generate 30 days of OHLCV
      const priceRecords = [];
      let lastClose = item.basePrice;

      for (let i = 29; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);

        // Skip weekends
        const day = date.getDay();
        if (day === 0 || day === 6) continue;

        const timeId = formatTimeId(date);

        // Calculate daily price change (within -5% to +5%)
        const pctChange = (Math.random() * 10 - 5) / 100;
        const change = Math.round(lastClose * pctChange);
        const open = lastClose;
        const close = open + change;
        const high = Math.max(open, close) + Math.round(Math.random() * (open * 0.02));
        const low = Math.min(open, close) - Math.round(Math.random() * (open * 0.02));
        const volume = Math.round(item.vol * (0.8 + Math.random() * 0.4));
        const marketCap = close * 1000000000; // Mock outstanding shares

        priceRecords.push({
          stock_id: stock._id,
          market_id: hose._id,
          industry_id: item.industry?._id,
          data_source_id: ssi._id,
          time_id: timeId,
          open_price: open,
          high_price: high,
          low_price: low,
          close_price: close,
          volume,
          price_change: change,
          price_change_percent: Number((pctChange * 100).toFixed(2)),
          market_cap: marketCap,
          crawled_at: date
        });

        lastClose = close;
      }

      await FactMarketPrice.insertMany(priceRecords);
      console.log(`[Seed] Seeded ${priceRecords.length} price records for ${item.symbol}`);
    }

    console.log('[Seed] Stock and Market Price seeding completed successfully.');
  } catch (err) {
    console.error(`[Seed] Error seeding stocks and prices: ${err.message}`);
    throw err;
  }
};

module.exports = seedStocksAndPrices;
