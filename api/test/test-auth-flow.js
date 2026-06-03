const mongoose = require('mongoose');
const app = require('../src/app');
const connectDB = require('../src/config/database.config');
const seedRolesAndUsers = require('../src/database/seeds/seed-roles');

const TEST_PORT = 5001;
const BASE_URL = `http://localhost:${TEST_PORT}/api`;

const runTests = async () => {
  let server;
  try {
    console.log('=== STARTING INTEGRATION TESTS ===');

    // 1. Connect to Database and Seed
    await connectDB();
    await seedRolesAndUsers();

    // 2. Start HTTP Server on Test Port
    server = app.listen(TEST_PORT, () => {
      console.log(`[Test] HTTP server listening on port ${TEST_PORT}`);
    });

    let accessToken = '';
    let refreshToken = '';

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

    const getJson = async (path, headers = {}) => {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: 'GET',
        headers
      });
      const data = await response.json();
      return { status: response.status, data };
    };

    // TC-AUTH-00: Đăng ký tài khoản mới thành công
    console.log('\nTC-AUTH-00: Register a new user...');
    const testRegisterEmail = `newuser_${Date.now()}@example.com`;
    const registerRes = await postJson('/auth/register', {
      full_name: 'Test New User',
      email: testRegisterEmail,
      password: 'newuser123456'
    });
    console.log(`Status: ${registerRes.status}`);
    console.log('Body:', JSON.stringify(registerRes.data, null, 2));
    if (registerRes.status !== 201 || !registerRes.data.success || !registerRes.data.data.user || registerRes.data.data.user.email !== testRegisterEmail) {
      throw new Error('TC-AUTH-00: Registration Failed');
    }
    console.log('✓ TC-AUTH-00: Registration Passed');

    // TC-AUTH-00.1: Đăng ký trùng email
    console.log('\nTC-AUTH-00.1: Register duplicate email...');
    const dupRegisterRes = await postJson('/auth/register', {
      full_name: 'Duplicate User',
      email: testRegisterEmail,
      password: 'newuser123456'
    });
    console.log(`Status: ${dupRegisterRes.status}`);
    console.log('Body:', JSON.stringify(dupRegisterRes.data, null, 2));
    if (dupRegisterRes.status !== 400 || dupRegisterRes.data.success || dupRegisterRes.data.message !== 'Email is already registered') {
      throw new Error('TC-AUTH-00.1: Duplicate Registration Detection Failed');
    }
    console.log('✓ TC-AUTH-00.1: Duplicate Registration Detection Passed');

    // TC-AUTH-00.2: Đăng ký sai thông tin (validation)
    console.log('\nTC-AUTH-00.2: Register with invalid validation payload...');
    const invalidRegisterRes = await postJson('/auth/register', {
      full_name: 'A', // too short
      email: 'invalid-email',
      password: 'short' // too short
    });
    console.log(`Status: ${invalidRegisterRes.status}`);
    console.log('Body:', JSON.stringify(invalidRegisterRes.data, null, 2));
    if (invalidRegisterRes.status !== 400 || invalidRegisterRes.data.success || !invalidRegisterRes.data.errors) {
      throw new Error('TC-AUTH-00.2: Registration Validation Failed to Catch Bad Payload');
    }
    console.log('✓ TC-AUTH-00.2: Registration Validation Passed');

    // TC-AUTH-00.3: Log in using the newly registered user
    console.log('\nTC-AUTH-00.3: Log in with newly registered user...');
    const newLoginRes = await postJson('/auth/login', {
      email: testRegisterEmail,
      password: 'newuser123456'
    });
    console.log(`Status: ${newLoginRes.status}`);
    console.log('Body:', JSON.stringify(newLoginRes.data, null, 2));
    if (newLoginRes.status !== 200 || !newLoginRes.data.success || !newLoginRes.data.data.access_token) {
      throw new Error('TC-AUTH-00.3: Log in with New User Failed');
    }
    console.log('✓ TC-AUTH-00.3: Log in with New User Passed');

    // TC-AUTH-01: Login đúng email/password
    console.log('\nTC-AUTH-01: Login with correct credentials...');
    const loginRes = await postJson('/auth/login', {
      email: 'user@example.com',
      password: 'user123456'
    });
    console.log(`Status: ${loginRes.status}`);
    console.log('Body:', JSON.stringify(loginRes.data, null, 2));
    if (loginRes.status !== 200 || !loginRes.data.success || !loginRes.data.data.access_token) {
      throw new Error('TC-AUTH-01 Failed');
    }
    accessToken = loginRes.data.data.access_token;
    refreshToken = loginRes.data.data.refresh_token;
    console.log('✓ TC-AUTH-01 Passed');

    // TC-AUTH-02: Login sai password
    console.log('\nTC-AUTH-02: Login with wrong password...');
    const wrongPassRes = await postJson('/auth/login', {
      email: 'user@example.com',
      password: 'wrongpassword'
    });
    console.log(`Status: ${wrongPassRes.status}`);
    console.log('Body:', JSON.stringify(wrongPassRes.data, null, 2));
    if (wrongPassRes.status !== 401 || wrongPassRes.data.success) {
      throw new Error('TC-AUTH-02 Failed');
    }
    console.log('✓ TC-AUTH-02 Passed');

    // TC-AUTH-03: Login email không tồn tại
    console.log('\nTC-AUTH-03: Login with non-existent email...');
    const nonExistentRes = await postJson('/auth/login', {
      email: 'nonexistent@example.com',
      password: 'somepassword'
    });
    console.log(`Status: ${nonExistentRes.status}`);
    console.log('Body:', JSON.stringify(nonExistentRes.data, null, 2));
    if (nonExistentRes.status !== 401 || nonExistentRes.data.success) {
      throw new Error('TC-AUTH-03 Failed');
    }
    console.log('✓ TC-AUTH-03 Passed');

    // TC-AUTH-04: Login tài khoản bị khóa
    console.log('\nTC-AUTH-04: Login with locked account...');
    const lockedRes = await postJson('/auth/login', {
      email: 'locked@example.com',
      password: 'locked123456'
    });
    console.log(`Status: ${lockedRes.status}`);
    console.log('Body:', JSON.stringify(lockedRes.data, null, 2));
    if (lockedRes.status !== 403 || lockedRes.data.success || lockedRes.data.message !== 'Account is locked') {
      throw new Error('TC-AUTH-04 Failed');
    }
    console.log('✓ TC-AUTH-04 Passed');

    // TC-AUTH-05: Gọi /users/me không có token
    console.log('\nTC-AUTH-05: Get /users/me without token...');
    const noTokenRes = await getJson('/users/me');
    console.log(`Status: ${noTokenRes.status}`);
    console.log('Body:', JSON.stringify(noTokenRes.data, null, 2));
    if (noTokenRes.status !== 401 || noTokenRes.data.success) {
      throw new Error('TC-AUTH-05 Failed');
    }
    console.log('✓ TC-AUTH-05 Passed');

    // TC-AUTH-06: Gọi /users/me với token hợp lệ
    console.log('\nTC-AUTH-06: Get /users/me with valid token...');
    const meRes = await getJson('/users/me', {
      Authorization: `Bearer ${accessToken}`
    });
    console.log(`Status: ${meRes.status}`);
    console.log('Body:', JSON.stringify(meRes.data, null, 2));
    if (meRes.status !== 200 || !meRes.data.success || meRes.data.data.email !== 'user@example.com' || meRes.data.data.role !== 'USER') {
      throw new Error('TC-AUTH-06 Failed');
    }
    console.log('✓ TC-AUTH-06 Passed');

    // TC-AUTH-08: Refresh token hợp lệ
    console.log('\nTC-AUTH-08: Refresh token...');
    const refreshRes = await postJson('/auth/refresh-token', {
      refresh_token: refreshToken
    });
    console.log(`Status: ${refreshRes.status}`);
    console.log('Body:', JSON.stringify(refreshRes.data, null, 2));
    if (refreshRes.status !== 200 || !refreshRes.data.success || !refreshRes.data.data.access_token) {
      throw new Error('TC-AUTH-08 Failed');
    }
    const newAccessToken = refreshRes.data.data.access_token;
    console.log('✓ TC-AUTH-08 Passed');

    // Verify the new access token works on /users/me
    console.log('\nTC-AUTH-08.1: Verify new access token...');
    const newMeRes = await getJson('/users/me', {
      Authorization: `Bearer ${newAccessToken}`
    });
    console.log(`Status: ${newMeRes.status}`);
    if (newMeRes.status !== 200 || !newMeRes.data.success) {
      throw new Error('TC-AUTH-08.1 Verification Failed');
    }
    console.log('✓ TC-AUTH-08.1 Verification Passed');

    // TC-AUTH-07: Logout thành công
    console.log('\nTC-AUTH-07: Logout...');
    const logoutRes = await postJson('/auth/logout', {}, {
      Authorization: `Bearer ${accessToken}`
    });
    console.log(`Status: ${logoutRes.status}`);
    console.log('Body:', JSON.stringify(logoutRes.data, null, 2));
    if (logoutRes.status !== 200 || !logoutRes.data.success || logoutRes.data.message !== 'Logout successfully') {
      throw new Error('TC-AUTH-07 Failed');
    }
    console.log('✓ TC-AUTH-07 Passed');

    // TC-SWAGGER: Verify Swagger UI HTML page loads
    console.log('\nTC-SWAGGER: Requesting Swagger UI endpoint...');
    const swaggerResponse = await fetch(`http://localhost:${TEST_PORT}/api-docs/`);
    console.log(`Status: ${swaggerResponse.status}`);
    if (swaggerResponse.status !== 200) {
      throw new Error('TC-SWAGGER Verification Failed');
    }
    const swaggerHtml = await swaggerResponse.text();
    if (!swaggerHtml.includes('<div id="swagger-ui">')) {
      throw new Error('TC-SWAGGER HTML Verification Failed');
    }
    console.log('✓ TC-SWAGGER Verification Passed');

    // TC-AUTH-09: Refresh token sai/hết hạn/đã logout
    console.log('\nTC-AUTH-09: Refresh token after logout...');
    const staleRefreshRes = await postJson('/auth/refresh-token', {
      refresh_token: refreshToken
    });
    console.log(`Status: ${staleRefreshRes.status}`);
    console.log('Body:', JSON.stringify(staleRefreshRes.data, null, 2));
    if (staleRefreshRes.status !== 401 || staleRefreshRes.data.success) {
      throw new Error('TC-AUTH-09 Failed');
    }
    console.log('✓ TC-AUTH-09 Passed');

    console.log('\n=== ALL INTEGRATION TESTS PASSED SUCCESSFULLY ===');
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
