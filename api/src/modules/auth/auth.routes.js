const express = require('express');
const router = express.Router();
const authController = require('./auth.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const { loginValidationRules, refreshTokenValidationRules, validate } = require('./auth.validation');

/**
 * @openapi
 * tags:
 *   name: Auth
 *   description: User authentication and token management
 */

/**
 * @openapi
 * /api/auth/login:
 *   post:
 *     summary: Log in a user
 *     description: Validate credentials and return standard user object and access/refresh tokens.
 *     tags: [Auth]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - email
 *               - password
 *             properties:
 *               email:
 *                 type: string
 *                 format: email
 *                 example: user@example.com
 *               password:
 *                 type: string
 *                 format: password
 *                 minLength: 8
 *                 example: user123456
 *     responses:
 *       200:
 *         description: Login successful. Returns access and refresh tokens.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Login successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     access_token:
 *                       type: string
 *                       example: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
 *                     refresh_token:
 *                       type: string
 *                       example: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
 *                     user:
 *                       type: object
 *                       properties:
 *                         id:
 *                           type: string
 *                           example: 6a1d3cacd1bbbbbbdaca6892
 *                         full_name:
 *                           type: string
 *                           example: Regular User
 *                         email:
 *                           type: string
 *                           example: user@example.com
 *                         role:
 *                           type: string
 *                           example: USER
 *                         status:
 *                           type: string
 *                           example: ACTIVE
 *       400:
 *         description: Validation failed (e.g. invalid email format or password too short).
 *       401:
 *         description: Invalid email or password.
 *       403:
 *         description: Account is locked or inactive.
 */
router.post('/login', loginValidationRules, validate, authController.login);

/**
 * @openapi
 * /api/auth/logout:
 *   post:
 *     summary: Log out current user
 *     description: Invalidate refresh token in database for the authorized user.
 *     tags: [Auth]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Logout successful.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Logout successfully
 *       401:
 *         description: Unauthorized. Missing or invalid Bearer access token.
 */
router.post('/logout', authMiddleware, authController.logout);

/**
 * @openapi
 * /api/auth/refresh-token:
 *   post:
 *     summary: Refresh access token
 *     description: Obtain a new short-lived access token using a valid long-lived refresh token.
 *     tags: [Auth]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - refresh_token
 *             properties:
 *               refresh_token:
 *                 type: string
 *                 example: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
 *     responses:
 *       200:
 *         description: Token successfully refreshed.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Refresh token successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     access_token:
 *                       type: string
 *                       example: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
 *       400:
 *         description: Validation failed. Missing refresh token in request body.
 *       401:
 *         description: Invalid refresh token.
 *       403:
 *         description: User account is not active.
 */
router.post('/refresh-token', refreshTokenValidationRules, validate, authController.refreshToken);

/**
 * @openapi
 * /api/auth/me:
 *   get:
 *     summary: Get current logged-in user profile
 *     description: Retrieve details of the user associated with the provided access token.
 *     tags: [Auth]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: User details successfully retrieved.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 data:
 *                   type: object
 *                   properties:
 *                     id:
 *                       type: string
 *                       example: 6a1d3cacd1bbbbbbdaca6892
 *                     full_name:
 *                       type: string
 *                       example: Regular User
 *                     email:
 *                       type: string
 *                       example: user@example.com
 *                     role:
 *                       type: string
 *                       example: USER
 *                     status:
 *                       type: string
 *                       example: ACTIVE
 *                     created_at:
 *                       type: string
 *                       format: date-time
 *                       example: 2026-06-01T00:00:00.000Z
 *       401:
 *         description: Unauthorized. Missing or invalid Bearer access token.
 *       403:
 *         description: Account is locked or inactive.
 */
router.get('/me', authMiddleware, authController.getMe);

module.exports = router;
