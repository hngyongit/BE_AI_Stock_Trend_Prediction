/**
 * Runner: Seed lại data cho các collection đã cập nhật schema
 * - dimMarkets
 * - dimIndustries
 * - dimDataSources
 *
 * Chạy: node src/database/seeds/run-seed-updated.js
 */

const mongoose = require('mongoose');
const connectDB = require('../../config/database.config');

const seedMarkets = require('./seed-markets');
const seedIndustries = require('./seed-industries');
const seedDataSources = require('./seed-data-sources');
const seedStocksAndPrices = require('./seed-stocks-prices');

const run = async () => {
  try {
    await connectDB();
    console.log('\n========================================');
    console.log('[Seed] Starting seed for updated collections...');
    console.log('========================================\n');

    // 1. Seed dimMarkets
    console.log('--- dimMarkets ---');
    await seedMarkets();

    // 2. Seed dimIndustries
    console.log('\n--- dimIndustries ---');
    await seedIndustries();

    // 3. Seed dimDataSources
    console.log('\n--- dimDataSources ---');
    await seedDataSources();

    // 4. Seed dimStocks and factMarketPrices
    console.log('\n--- dimStocks & factMarketPrices ---');
    await seedStocksAndPrices();

    console.log('\n========================================');
    console.log('[Seed] All done!');
    console.log('========================================\n');

    await mongoose.connection.close();
    process.exit(0);
  } catch (err) {
    console.error('[Seed] Error:', err.message);
    await mongoose.connection.close();
    process.exit(1);
  }
};

run();
