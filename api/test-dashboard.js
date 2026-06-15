const mongoose = require('mongoose');
const path = require('path');
const dotenv = require('dotenv');

// Load environment variables
dotenv.config({ path: path.resolve(__dirname, '../.env') });
dotenv.config({ path: path.resolve(__dirname, './.env') });

const connectDB = require('./src/config/database.config');
const dashboardService = require('./src/modules/dashboard/dashboard.service');
const User = require('./src/database/models/user.model');
const Role = require('./src/database/models/role.model');

const runTest = async () => {
  console.log('Connecting to database...');
  await connectDB();

  try {
    // 1. Get default users for each role
    const roles = await Role.find().lean();
    const userRole = roles.find(r => r.name === 'USER');
    const staffRole = roles.find(r => r.name === 'STAFF');
    const adminRole = roles.find(r => r.name === 'ADMIN');

    if (!userRole || !staffRole || !adminRole) {
      throw new Error('Default roles not found in the database. Ensure seeding has run.');
    }

    console.log('Roles found:', {
      USER: userRole._id,
      STAFF: staffRole._id,
      ADMIN: adminRole._id
    });

    const userAccount = await User.findOne({ role_id: userRole._id }).lean();
    const staffAccount = await User.findOne({ role_id: staffRole._id }).lean();
    const adminAccount = await User.findOne({ role_id: adminRole._id }).lean();

    if (!userAccount) console.log('Warning: No user account found.');
    if (!staffAccount) console.log('Warning: No staff account found.');
    if (!adminAccount) console.log('Warning: No admin account found.');

    // 2. Test User Dashboard Service
    if (userAccount) {
      console.log(`\n--- Testing USER Dashboard for User: ${userAccount.email} ---`);
      const userDashboardData = await dashboardService.getUserDashboard(userAccount._id);
      console.log('USER Dashboard Data Output:');
      console.log(JSON.stringify(userDashboardData, null, 2));

      // Assert basic structure
      if (!userDashboardData.watchlist || !userDashboardData.market_leaders) {
        throw new Error('USER dashboard structure is invalid');
      }
      console.log('USER Dashboard: SUCCESS');
    }

    // 3. Test Staff Dashboard Service
    console.log(`\n--- Testing STAFF Dashboard ---`);
    const staffDashboardData = await dashboardService.getStaffDashboard();
    console.log('STAFF Dashboard Data Output:');
    console.log(JSON.stringify(staffDashboardData, null, 2));
    if (!staffDashboardData.jobs || !staffDashboardData.logs || !staffDashboardData.catalog || !staffDashboardData.recent_activities) {
      throw new Error('STAFF dashboard structure is invalid');
    }
    console.log('STAFF Dashboard: SUCCESS');

    // 4. Test Admin Dashboard Service
    console.log(`\n--- Testing ADMIN Dashboard ---`);
    const adminDashboardData = await dashboardService.getAdminDashboard();
    console.log('ADMIN Dashboard Data Output:');
    console.log(JSON.stringify(adminDashboardData, null, 2));
    if (!adminDashboardData.users || !adminDashboardData.watchlists || !adminDashboardData.catalog || !adminDashboardData.system_health) {
      throw new Error('ADMIN dashboard structure is invalid');
    }
    console.log('ADMIN Dashboard: SUCCESS');

    console.log('\n========================================');
    console.log('ALL SERVICE LAYER TESTS COMPLETED SUCCESSFULLY!');
    console.log('========================================');

  } catch (error) {
    console.error('Test execution failed:', error);
    process.exit(1);
  } finally {
    await mongoose.connection.close();
    console.log('Database connection closed.');
  }
};

runTest();
