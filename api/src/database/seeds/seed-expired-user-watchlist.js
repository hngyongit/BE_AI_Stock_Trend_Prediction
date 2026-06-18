/**
 * Seed script: Add stock symbols to expired@example.com watchlist
 *
 * This script:
 * 1. Finds the expired Pro user (expired@example.com)
 * 2. Looks up some popular stock symbols in dimstocks
 * 3. Adds them to the user's watchlist (6 stocks — exceeds FREE limit of 5)
 *
 * Run directly: node src/database/seeds/seed-expired-user-watchlist.js
 */

const mongoose = require('mongoose');
const User = require('../models/user.model');
const DimStock = require('../models/dim-stock.model');
const Watchlist = require('../models/watchlist.model');
const connectDB = require('../../config/database.config');

const STOCK_SYMBOLS = ['FPT', 'VCB', 'ACB', 'VNM', 'HPG', 'VIC'];

async function seedExpiredUserWatchlist() {
  try {
    // 1. Find the expired user
    const user = await User.findOne({ email: 'expired@example.com' });
    if (!user) {
      console.error('[Seed] ❌ Expired user not found! Run seed-roles.js first.');
      process.exit(1);
    }
    console.log(`[Seed] ✅ Found user: ${user.full_name} (${user.email})`);
    console.log(`[Seed]    Current plan: ${user.plan}, subscription_status: ${user.subscription_status}`);

    // 2. Find stocks by symbol
    const stocks = await DimStock.find({ symbol: { $in: STOCK_SYMBOLS } });
    if (stocks.length === 0) {
      console.error('[Seed] ❌ No stocks found in database. Run crawler or seed stocks first.');
      console.log('[Seed]    Expected symbols: ' + STOCK_SYMBOLS.join(', '));
      process.exit(1);
    }

    console.log(`[Seed] ✅ Found ${stocks.length}/${STOCK_SYMBOLS.length} stocks:`);
    for (const s of stocks) {
      console.log(`       - ${s.symbol}: ${s.company_name}`);
    }

    if (stocks.length < STOCK_SYMBOLS.length) {
      const foundSymbols = stocks.map(s => s.symbol);
      const missing = STOCK_SYMBOLS.filter(sym => !foundSymbols.includes(sym));
      console.warn(`[Seed] ⚠️  Missing symbols: ${missing.join(', ')}`);
    }

    // 3. Add stocks to watchlist (skip if already exists)
    let addedCount = 0;
    let skippedCount = 0;

    for (const stock of stocks) {
      const exists = await Watchlist.findOne({
        user_id: user._id,
        stock_id: stock._id
      });

      if (!exists) {
        await Watchlist.create({
          user_id: user._id,
          stock_id: stock._id
        });
        console.log(`[Seed]   ➕ Added ${stock.symbol} to watchlist`);
        addedCount++;
      } else {
        console.log(`[Seed]   ⏭️  ${stock.symbol} already in watchlist`);
        skippedCount++;
      }
    }

    // 4. Show summary
    const totalInWatchlist = await Watchlist.countDocuments({ user_id: user._id });
    console.log('\n[Seed] ───────────────────────────────────────');
    console.log(`[Seed] ✅ Done!`);
    console.log(`[Seed]    Added:     ${addedCount}`);
    console.log(`[Seed]    Skipped:   ${skippedCount}`);
    console.log(`[Seed]    Total in watchlist: ${totalInWatchlist}`);
    console.log(`[Seed]    FREE limit: 5 — overLimit: ${totalInWatchlist > 5 ? '✅ YES (trim flow testable)' : '❌ NO'}`);
    console.log('[Seed] ───────────────────────────────────────');
    console.log('\n[Seed] 💡 Now you can:');
    console.log(`[Seed]    1. GET  /api/watchlists (with expired@example.com token) → see overLimit response`);
    console.log(`[Seed]    2. POST /api/watchlists/trim { keepStockIds: [...] } → trim to fit FREE limit`);
    console.log(`[Seed]    3. POST /api/watchlists (add another) → should fail with "limit exceeded"`);

  } catch (error) {
    console.error(`[Seed] ❌ Error: ${error.message}`);
    throw error;
  }
}

// Run directly
if (require.main === module) {
  (async () => {
    await connectDB();
    await seedExpiredUserWatchlist();
    await mongoose.connection.close();
    process.exit(0);
  })();
}

module.exports = seedExpiredUserWatchlist;
