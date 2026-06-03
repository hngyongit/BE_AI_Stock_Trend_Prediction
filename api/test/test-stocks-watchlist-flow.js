const mongoose = require('mongoose');
const app = require('../src/app');
const connectDB = require('../src/config/database.config');
const bcrypt = require('bcryptjs');
const User = require('../src/database/models/user.model');
const Watchlist = require('../src/database/models/watchlist.model');
const env = require('../src/config/env.config');

// Seeds
const seedRolesAndUsers = require('../src/database/seeds/seed-roles');
const seedMarkets = require('../src/database/seeds/seed-markets');
const seedIndustries = require('../src/database/seeds/seed-industries');
const seedDataSources = require('../src/database/seeds/seed-data-sources');
const seedStocksAndPrices = require('../src/database/seeds/seed-stocks-prices');

const TEST_PORT = 5003;
const BASE_URL = `http://localhost:${TEST_PORT}/api`;

const runTests = async () => {
  let server;
  try {
    console.log('=== STARTING STOCKS & WATCHLIST INTEGRATION TESTS ===');

    // 1. Connect to database
    await connectDB();

    // 2. Clear & Seed Database sequentially
    console.log('\n[Test] Seeding database...');
    await seedRolesAndUsers();
    await seedMarkets();
    await seedIndustries();
    await seedDataSources();
    await seedStocksAndPrices();
    await Watchlist.deleteMany({});

    // 2.1. Reset test user passwords to guarantee test validity
    const saltRounds = env.BCRYPT_SALT_ROUNDS || 10;
    const testUsers = [
      { email: 'user@example.com', password: 'user123456' },
      { email: 'admin@example.com', password: 'admin123456' }
    ];

    for (const tu of testUsers) {
      const u = await User.findOne({ email: tu.email });
      if (u) {
        const hashedPassword = await bcrypt.hash(tu.password, saltRounds);
        u.password_hash = hashedPassword;
        u.status = 'ACTIVE';
        await u.save();
        console.log(`[Test Prep] Password reset for ${tu.email}`);
      }
    }

    console.log('[Test] Database seeding & prep complete.');

    // 3. Start HTTP Server on Test Port
    server = app.listen(TEST_PORT, () => {
      console.log(`[Test] HTTP server listening on port ${TEST_PORT}`);
    });

    let userToken = '';
    let adminToken = '';

    // Helpers for request
    const postJson = async (path, body, headers = {}) => {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify(body)
      });
      const data = await response.json();
      return { status: response.status, data };
    };

    const putJson = async (path, body, headers = {}) => {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify(body)
      });
      const data = await response.json();
      return { status: response.status, data };
    };

    const deleteJson = async (path, headers = {}) => {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: 'DELETE',
        headers
      });
      const data = await response.json();
      return { status: response.status, data };
    };

    const getJson = async (path, headers = {}) => {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: 'GET',
        headers
      });
      const data = await response.json();
      return { status: response.status, data };
    };

    // Obtain access tokens
    console.log('\n[Test] Logging in test users...');
    const userLogin = await postJson('/auth/login', { email: 'user@example.com', password: 'user123456' });
    userToken = userLogin.data.data.access_token;

    const adminLogin = await postJson('/auth/login', { email: 'admin@example.com', password: 'admin123456' });
    adminToken = adminLogin.data.data.access_token;
    console.log('[Test] Tokens obtained successfully.');


    // TC-STOCK-01: List Stocks
    console.log('\nTC-STOCK-01: Retrieve stock list...');
    const listRes = await getJson('/stocks?market=HOSE&limit=5');
    console.log(`Status: ${listRes.status}`);
    console.log(`Items count: ${listRes.data.data.items.length}`);
    if (listRes.status !== 200 || !listRes.data.success || listRes.data.data.items.length === 0) {
      throw new Error('TC-STOCK-01 Failed');
    }
    console.log('✓ TC-STOCK-01 Passed');


    // TC-STOCK-02: Detail Stock
    console.log('\nTC-STOCK-02: Get FPT stock details...');
    const detailRes = await getJson('/stocks/FPT');
    console.log(`Status: ${detailRes.status}`);
    console.log('Latest Price:', JSON.stringify(detailRes.data.data.latest_price, null, 2));
    if (detailRes.status !== 200 || detailRes.data.data.symbol !== 'FPT' || !detailRes.data.data.latest_price) {
      throw new Error('TC-STOCK-02 Failed');
    }

    console.log('TC-STOCK-02.1: Get non-existent stock details...');
    const invalidDetailRes = await getJson('/stocks/INVALID');
    console.log(`Status: ${invalidDetailRes.status}`);
    if (invalidDetailRes.status !== 404 || invalidDetailRes.data.success) {
      throw new Error('TC-STOCK-02.1 Failed');
    }
    console.log('✓ TC-STOCK-02 Passed');


    // TC-STOCK-03: Stock Price Chart
    console.log('\nTC-STOCK-03: Get FPT stock chart history (7d)...');
    const chartRes = await getJson('/stocks/FPT/chart?range=7d');
    console.log(`Status: ${chartRes.status}`);
    console.log(`Chart points: ${chartRes.data.data.length}`);
    if (chartRes.status !== 200 || !Array.isArray(chartRes.data.data)) {
      throw new Error('TC-STOCK-03 Failed');
    }
    console.log('✓ TC-STOCK-03 Passed');


    // TC-AD-STOCK-01: Admin creates a new stock
    console.log('\nTC-AD-STOCK-01: Admin creates MWG stock...');
    const addMwgRes = await postJson('/admin/stocks', {
      symbol: 'MWG',
      company_name: 'Thế giới Di động',
      exchange_code: 'HOSE',
      status: 'ACTIVE',
      listed_date: '2014-07-14'
    }, { Authorization: `Bearer ${adminToken}` });
    console.log(`Status: ${addMwgRes.status}`);
    console.log('Body:', JSON.stringify(addMwgRes.data, null, 2));
    if (addMwgRes.status !== 201 || addMwgRes.data.data.symbol !== 'MWG') {
      throw new Error('TC-AD-STOCK-01 Failed');
    }
    const mwgId = addMwgRes.data.data.id;
    console.log('✓ TC-AD-STOCK-01 Passed');


    // TC-AD-STOCK-02: Regular user creates stock (expects 403)
    console.log('\nTC-AD-STOCK-02: User tries to create stock (should fail)...');
    const failAddRes = await postJson('/admin/stocks', {
      symbol: 'MSN',
      company_name: 'Masan Group',
      exchange_code: 'HOSE'
    }, { Authorization: `Bearer ${userToken}` });
    console.log(`Status: ${failAddRes.status}`);
    if (failAddRes.status !== 403 || failAddRes.data.success) {
      throw new Error('TC-AD-STOCK-02 Failed');
    }
    console.log('✓ TC-AD-STOCK-02 Passed');


    // TC-AD-STOCK-03: Admin updates stock MWG
    console.log('\nTC-AD-STOCK-03: Admin updates MWG status to SUSPENDED...');
    const updateRes = await putJson(`/admin/stocks/${mwgId}`, {
      status: 'SUSPENDED'
    }, { Authorization: `Bearer ${adminToken}` });
    console.log(`Status: ${updateRes.status}`);
    console.log('Body:', JSON.stringify(updateRes.data, null, 2));
    if (updateRes.status !== 200 || updateRes.data.data.status !== 'SUSPENDED') {
      throw new Error('TC-AD-STOCK-03 Failed');
    }
    console.log('✓ TC-AD-STOCK-03 Passed');


    // TC-WATCH-01: Add stocks to Watchlist
    console.log('\nTC-WATCH-01: Add FPT, HPG, VNM, VIC, TCB to personal watchlist...');
    const symbols = ['FPT', 'HPG', 'VNM', 'VIC', 'TCB'];
    for (const sym of symbols) {
      const addRes = await postJson('/watchlists', { symbol: sym }, { Authorization: `Bearer ${userToken}` });
      console.log(`Added ${sym}: Status ${addRes.status}`);
      if (addRes.status !== 201 || !addRes.data.success) {
        throw new Error(`Failed to add ${sym} to watchlist`);
      }
    }
    console.log('✓ TC-WATCH-01 Passed');


    // TC-WATCH-02: Watchlist limit exceeded (max 5)
    console.log('\nTC-WATCH-02: Try to add 6th stock (MWG) to watchlist (should fail)...');
    const addSixthRes = await postJson('/watchlists', { symbol: 'MWG' }, { Authorization: `Bearer ${userToken}` });
    console.log(`Status: ${addSixthRes.status}`);
    console.log('Body:', JSON.stringify(addSixthRes.data, null, 2));
    if (addSixthRes.status !== 400 || addSixthRes.data.message !== 'Watchlist limit exceeded (Maximum 5 stocks allowed)') {
      throw new Error('TC-WATCH-02 Failed');
    }
    console.log('✓ TC-WATCH-02 Passed');


    // TC-WATCH-03: Add duplicate stock
    console.log('\nTC-WATCH-03: Try to add duplicate FPT to watchlist (should fail)...');
    const addDupRes = await postJson('/watchlists', { symbol: 'FPT' }, { Authorization: `Bearer ${userToken}` });
    console.log(`Status: ${addDupRes.status}`);
    console.log('Body:', JSON.stringify(addDupRes.data, null, 2));
    if (addDupRes.status !== 400 || addDupRes.data.message !== 'Stock is already in your watchlist') {
      throw new Error('TC-WATCH-03 Failed');
    }
    console.log('✓ TC-WATCH-03 Passed');


    // TC-WATCH-04: Add non-existent stock
    console.log('\nTC-WATCH-04: Try to add non-existent stock XYZ (should fail)...');
    const addNonExistRes = await postJson('/watchlists', { symbol: 'XYZ' }, { Authorization: `Bearer ${userToken}` });
    console.log(`Status: ${addNonExistRes.status}`);
    console.log('Body:', JSON.stringify(addNonExistRes.data, null, 2));
    if (addNonExistRes.status !== 404 || addNonExistRes.data.message !== 'Stock symbol not found') {
      throw new Error('TC-WATCH-04 Failed');
    }
    console.log('✓ TC-WATCH-04 Passed');


    // TC-WATCH-05: View Watchlist
    console.log('\nTC-WATCH-05: Get personal watchlist...');
    const viewRes = await getJson('/watchlists', { Authorization: `Bearer ${userToken}` });
    console.log(`Status: ${viewRes.status}`);
    console.log(`Watchlist count: ${viewRes.data.data.length}`);
    if (viewRes.status !== 200 || viewRes.data.data.length !== 5 || !viewRes.data.data[0].latest_price) {
      throw new Error('TC-WATCH-05 Failed');
    }
    console.log('✓ TC-WATCH-05 Passed');


    // TC-WATCH-06: Remove Stock from Watchlist
    console.log('\nTC-WATCH-06: Remove FPT from watchlist...');
    const deleteRes = await deleteJson('/watchlists/FPT', { Authorization: `Bearer ${userToken}` });
    console.log(`Status: ${deleteRes.status}`);
    if (deleteRes.status !== 200) {
      throw new Error('TC-WATCH-06 Failed');
    }

    console.log('TC-WATCH-06.1: Verify watchlist size is now 4...');
    const viewRes2 = await getJson('/watchlists', { Authorization: `Bearer ${userToken}` });
    console.log(`New size: ${viewRes2.data.data.length}`);
    if (viewRes2.data.data.length !== 4) {
      throw new Error('TC-WATCH-06.1 Failed');
    }

    console.log('TC-WATCH-06.2: Try to delete FPT again (should fail)...');
    const deleteRes2 = await deleteJson('/watchlists/FPT', { Authorization: `Bearer ${userToken}` });
    console.log(`Status: ${deleteRes2.status}`);
    if (deleteRes2.status !== 404 || deleteRes2.data.message !== 'Stock not found in your watchlist') {
      throw new Error('TC-WATCH-06.2 Failed');
    }
    console.log('✓ TC-WATCH-06 Passed');

    console.log('\n=== ALL STOCKS & WATCHLIST TESTS PASSED SUCCESSFULLY ===');
  } catch (error) {
    console.error(`\n✖ Test runner failed: ${error.message}`);
    process.exitCode = 1;
  } finally {
    if (server) {
      console.log('\n[Test] Closing HTTP server...');
      await new Promise((resolve) => server.close(resolve));
    }
    console.log('[Test] Closing MongoDB connection...');
    await mongoose.connection.close();
    console.log('[Test] Completed cleanup. Exiting.');
    process.exit(process.exitCode || 0);
  }
};

runTests();
