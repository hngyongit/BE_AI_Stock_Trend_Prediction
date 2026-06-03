const mongoose = require('mongoose');
const app = require('../src/app');
const connectDB = require('../src/config/database.config');
const seedRolesAndUsers = require('../src/database/seeds/seed-roles');

const TEST_PORT = 5002;
const BASE_URL = `http://localhost:${TEST_PORT}/api`;

const runTests = async () => {
  let server;
  try {
    console.log('=== STARTING USER MANAGEMENT INTEGRATION TESTS ===');

    // 1. Connect and Seed
    await connectDB();
    await seedRolesAndUsers();

    // 2. Start HTTP Server
    server = app.listen(TEST_PORT, () => {
      console.log(`[Test] HTTP server listening on port ${TEST_PORT}`);
    });

    // Request helpers
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

    const getJson = async (path, headers = {}) => {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: 'GET',
        headers
      });
      const data = await response.json();
      return { status: response.status, data };
    };

    const patchJson = async (path, body = {}, headers = {}) => {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify(body)
      });
      const data = await response.json();
      return { status: response.status, data };
    };

    let userToken = '';
    let adminToken = '';
    let userId = '';
    let adminId = '';

    // ==========================================
    // TC-USER-01: Login as Regular User & Admin
    // ==========================================
    console.log('\nTC-USER-01: Authenticate user & admin...');
    
    const loginUserRes = await postJson('/auth/login', {
      email: 'user@example.com',
      password: 'user123456'
    });
    if (loginUserRes.status !== 200) throw new Error('User login failed');
    userToken = loginUserRes.data.data.access_token;
    userId = loginUserRes.data.data.user.id;

    const loginAdminRes = await postJson('/auth/login', {
      email: 'admin@example.com',
      password: 'admin123456'
    });
    if (loginAdminRes.status !== 200) throw new Error('Admin login failed');
    adminToken = loginAdminRes.data.data.access_token;
    adminId = loginAdminRes.data.data.user.id;

    console.log('✓ TC-USER-01 Passed');

    // ==========================================
    // TC-USER-02: Get Profile (/me)
    // ==========================================
    console.log('\nTC-USER-02: Get personal profile...');
    const meRes = await getJson('/users/me', {
      Authorization: `Bearer ${userToken}`
    });
    console.log(`Status: ${meRes.status}`);
    console.log('Body:', JSON.stringify(meRes.data, null, 2));
    if (meRes.status !== 200 || meRes.data.data.email !== 'user@example.com') {
      throw new Error('TC-USER-02 Failed');
    }
    console.log('✓ TC-USER-02 Passed');

    // ==========================================
    // TC-USER-03: Update Profile Name
    // ==========================================
    console.log('\nTC-USER-03: Update profile name...');
    const updateRes = await putJson('/users/me', {
      full_name: 'Regular User Updated'
    }, {
      Authorization: `Bearer ${userToken}`
    });
    console.log(`Status: ${updateRes.status}`);
    console.log('Body:', JSON.stringify(updateRes.data, null, 2));
    if (updateRes.status !== 200 || updateRes.data.data.full_name !== 'Regular User Updated') {
      throw new Error('TC-USER-03 Failed');
    }
    console.log('✓ TC-USER-03 Passed');

    // ==========================================
    // TC-USER-04: Change Password
    // ==========================================
    console.log('\nTC-USER-04: Change user password...');
    const passRes = await putJson('/users/me/password', {
      current_password: 'user123456',
      new_password: 'user12345678'
    }, {
      Authorization: `Bearer ${userToken}`
    });
    console.log(`Status: ${passRes.status}`);
    console.log('Body:', JSON.stringify(passRes.data, null, 2));
    if (passRes.status !== 200 || !passRes.data.success) {
      throw new Error('TC-USER-04 Failed');
    }

    // Verify login with new password works
    console.log('\nTC-USER-04.1: Verify login with new password...');
    const newLoginRes = await postJson('/auth/login', {
      email: 'user@example.com',
      password: 'user12345678'
    });
    console.log(`Status: ${newLoginRes.status}`);
    if (newLoginRes.status !== 200 || !newLoginRes.data.success) {
      throw new Error('TC-USER-04.1 Failed');
    }
    userToken = newLoginRes.data.data.access_token; // update userToken
    console.log('✓ TC-USER-04 Passed');

    // ==========================================
    // TC-USER-05: Admin View List of Users
    // ==========================================
    console.log('\nTC-USER-05: Admin list users...');
    const listRes = await getJson('/admin/users?keyword=Regular', {
      Authorization: `Bearer ${adminToken}`
    });
    console.log(`Status: ${listRes.status}`);
    console.log('Body:', JSON.stringify(listRes.data, null, 2));
    if (listRes.status !== 200 || listRes.data.data.items.length === 0) {
      throw new Error('TC-USER-05 Failed');
    }
    console.log('✓ TC-USER-05 Passed');

    // ==========================================
    // TC-USER-06: Admin View Detail
    // ==========================================
    console.log('\nTC-USER-06: Admin get user detail...');
    const detailRes = await getJson(`/admin/users/${userId}`, {
      Authorization: `Bearer ${adminToken}`
    });
    console.log(`Status: ${detailRes.status}`);
    console.log('Body:', JSON.stringify(detailRes.data, null, 2));
    if (detailRes.status !== 200 || detailRes.data.data.id !== userId) {
      throw new Error('TC-USER-06 Failed');
    }
    console.log('✓ TC-USER-06 Passed');

    // ==========================================
    // TC-USER-07: Admin Lock User Account
    // ==========================================
    console.log('\nTC-USER-07: Admin lock user account...');
    const lockRes = await patchJson(`/admin/users/${userId}/lock`, {}, {
      Authorization: `Bearer ${adminToken}`
    });
    console.log(`Status: ${lockRes.status}`);
    if (lockRes.status !== 200 || !lockRes.data.success) {
      throw new Error('TC-USER-07 Failed');
    }

    // Verify locked user cannot log in
    console.log('\nTC-USER-07.1: Verify login fails for locked user...');
    const lockedLoginRes = await postJson('/auth/login', {
      email: 'user@example.com',
      password: 'user12345678'
    });
    console.log(`Status: ${lockedLoginRes.status}`);
    console.log('Body:', JSON.stringify(lockedLoginRes.data, null, 2));
    if (lockedLoginRes.status !== 403 || lockedLoginRes.data.message !== 'Account is locked') {
      throw new Error('TC-USER-07.1 Verification Failed');
    }
    console.log('✓ TC-USER-07 Passed');

    // ==========================================
    // TC-USER-08: Admin Unlock User Account
    // ==========================================
    console.log('\nTC-USER-08: Admin unlock user account...');
    const unlockRes = await patchJson(`/admin/users/${userId}/unlock`, {}, {
      Authorization: `Bearer ${adminToken}`
    });
    console.log(`Status: ${unlockRes.status}`);
    if (unlockRes.status !== 200 || !unlockRes.data.success) {
      throw new Error('TC-USER-08 Failed');
    }

    // Verify user can login again
    console.log('\nTC-USER-08.1: Verify login succeeds for unlocked user...');
    const unlockedLoginRes = await postJson('/auth/login', {
      email: 'user@example.com',
      password: 'user12345678'
    });
    console.log(`Status: ${unlockedLoginRes.status}`);
    if (unlockedLoginRes.status !== 200) {
      throw new Error('TC-USER-08.1 Verification Failed');
    }
    userToken = unlockedLoginRes.data.data.access_token;
    console.log('✓ TC-USER-08 Passed');

    // ==========================================
    // TC-USER-09: Admin Update User Role
    // ==========================================
    console.log('\nTC-USER-09: Admin assign role STAFF to user...');
    const roleRes = await patchJson(`/admin/users/${userId}/role`, {
      role: 'STAFF'
    }, {
      Authorization: `Bearer ${adminToken}`
    });
    console.log(`Status: ${roleRes.status}`);
    console.log('Body:', JSON.stringify(roleRes.data, null, 2));
    if (roleRes.status !== 200 || roleRes.data.data.role !== 'STAFF') {
      throw new Error('TC-USER-09 Failed');
    }
    console.log('✓ TC-USER-09 Passed');

    // ==========================================
    // TC-USER-10: Security Guards Checks
    // ==========================================
    console.log('\nTC-USER-10: Security check - User accessing admin endpoint...');
    const blockedRes = await getJson('/admin/users', {
      Authorization: `Bearer ${userToken}` // STAFF token, should be blocked (only ADMIN allowed)
    });
    console.log(`Status: ${blockedRes.status}`);
    console.log('Body:', JSON.stringify(blockedRes.data, null, 2));
    if (blockedRes.status !== 403 || blockedRes.data.message !== 'Forbidden') {
      throw new Error('TC-USER-10 Block Check Failed');
    }

    console.log('\nTC-USER-10.1: Security check - Admin locking themselves...');
    const selfLockRes = await patchJson(`/admin/users/${adminId}/lock`, {}, {
      Authorization: `Bearer ${adminToken}`
    });
    console.log(`Status: ${selfLockRes.status}`);
    console.log('Body:', JSON.stringify(selfLockRes.data, null, 2));
    if (selfLockRes.status !== 400 || selfLockRes.data.message !== 'Admin cannot lock themselves or other admin accounts') {
      throw new Error('TC-USER-10.1 Self-Lock Block Check Failed');
    }
    console.log('✓ TC-USER-10 passed');

    // ==========================================
    // TC-USER-CLEANUP: Revert user password & role
    // ==========================================
    console.log('\nTC-USER-CLEANUP: Reverting password and role...');
    // Revert role
    await patchJson(`/admin/users/${userId}/role`, { role: 'USER' }, { Authorization: `Bearer ${adminToken}` });
    // Revert password
    await putJson('/users/me/password', { current_password: 'user12345678', new_password: 'user123456' }, { Authorization: `Bearer ${userToken}` });
    console.log('✓ Cleanup completed.');

    console.log('\n=== ALL USER MANAGEMENT INTEGRATION TESTS PASSED SUCCESSFULLY ===');
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
