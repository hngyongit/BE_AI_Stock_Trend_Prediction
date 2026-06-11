const express = require('express');
const passport = require('passport');
const router = express.Router();
const env = require('../../config/env.config');
const { error } = require('../../common/utils/response.util');
const authController = require('./auth.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const {
  loginValidationRules,
  refreshTokenValidationRules,
  registerValidationRules,
  oauthExchangeValidationRules,
  validate
} = require('./auth.validation');

const ensureGoogleOAuthConfigured = (req, res, next) => {
  if (!env.GOOGLE_CLIENT_ID || !env.GOOGLE_CLIENT_SECRET) {
    return error(res, 'Google OAuth is not configured', null, 503);
  }
  next();
};

const googleOAuthFailureRedirect =
  env.GOOGLE_OAUTH_FAILURE_REDIRECT ||
  `${env.GOOGLE_OAUTH_SUCCESS_REDIRECT.replace(/\/$/, '')}?error=google_auth_failed`;

const googleOAuthScope = { scope: ['profile', 'email'] };

const startGoogleLogin = (req, res, next) => {
  delete req.session.googleOAuthMode;
  req.session.save((err) => {
    if (err) return next(err);
    passport.authenticate('google', googleOAuthScope)(req, res, next);
  });
};

const startGoogleRegister = (req, res, next) => {
  req.session.googleOAuthMode = 'signup';
  req.session.save((err) => {
    if (err) return next(err);
    passport.authenticate('google', googleOAuthScope)(req, res, next);
  });
};

const googleOAuthCallbackHandler = (req, res, next) => {
  passport.authenticate('google', (err, user) => {
    if (err && err.statusCode === 409) {
      const base = env.GOOGLE_OAUTH_SUCCESS_REDIRECT.replace(/\/$/, '');
      const sep = base.includes('?') ? '&' : '?';
      delete req.session.googleOAuthMode;
      return req.session.save((saveErr) => {
        if (saveErr) return next(saveErr);
        return res.redirect(`${base}${sep}error=email_already_registered`);
      });
    }
    if (err) return next(err);
    if (!user) return res.redirect(googleOAuthFailureRedirect);
    req.user = user;
    delete req.session.googleOAuthMode;
    req.session.save((saveErr) => {
      if (saveErr) return next(saveErr);
      return authController.googleCallback(req, res, next);
    });
  })(req, res, next);
};

/**
 * @openapi
 * tags:
 *   name: Auth
 *   description: User authentication and token management
 */

/**
 * @openapi
 * /api/auth/google:
 *   get:
 *     summary: Start Google OAuth (sign in)
 *     description: Redirects to Google. Existing email accounts can be linked when email is verified on Google. Use `/google/register` for sign-up-only (reject if email already exists).
 *     tags: [Auth]
 *     responses:
 *       302:
 *         description: Redirect to Google authorization page.
 *       503:
 *         description: Google OAuth is not configured on the server.
 */
router.get('/google', ensureGoogleOAuthConfigured, startGoogleLogin);

/**
 * @openapi
 * /api/auth/google/register:
 *   get:
 *     summary: Start Google OAuth (sign up)
 *     description: Same Google flow as sign-in, but if the email already belongs to another account (e.g. registered with password), the user is redirected back with `error=email_already_registered` instead of linking.
 *     tags: [Auth]
 *     responses:
 *       302:
 *         description: Redirect to Google authorization page.
 *       503:
 *         description: Google OAuth is not configured on the server.
 */
router.get('/google/register', ensureGoogleOAuthConfigured, startGoogleRegister);

if (env.NODE_ENV === 'development') {
  router.get('/google/oauth-config', (req, res) => {
    res.json({
      GOOGLE_CALLBACK_URL: env.GOOGLE_CALLBACK_URL,
      hints: [
        'Paste GOOGLE_CALLBACK_URL into Google Cloud → APIs & Credentials → your OAuth client → Authorized redirect URIs (exact match).',
        'If you open Google login from a public API URL (e.g. DigitalOcean), set GOOGLE_CALLBACK_URL on that server to https://your-domain/api/auth/google/callback — not http://localhost:5000/...',
        'If you use 127.0.0.1 in the browser, add a separate redirect URI for http://127.0.0.1:5000/api/auth/google/callback or always use http://localhost:5000.'
      ]
    });
  });
}

/**
 * @openapi
 * /api/auth/google/callback:
 *   get:
 *     summary: Google OAuth callback
 *     description: |
 *       Completes Google login or register, then redirects to GOOGLE_OAUTH_SUCCESS_REDIRECT with a one-time `code` query param (or `error=email_already_registered` after sign-up if email is taken, or `error=google_auth_failed` on auth failure).
 *       Exchange a success `code` via POST /api/auth/oauth/exchange for JWTs.
 *     tags: [Auth]
 *     responses:
 *       302:
 *         description: Redirect to frontend with ?code=..., ?error=email_already_registered, or ?error=google_auth_failed
 *       503:
 *         description: Google OAuth is not configured on the server.
 */
router.get(
  '/google/callback',
  ensureGoogleOAuthConfigured,
  googleOAuthCallbackHandler
);

/**
 * @openapi
 * /api/auth/oauth/exchange:
 *   post:
 *     summary: Exchange Google OAuth one-time code for tokens
 *     description: |
 *       After Google login, the user lands on the frontend with `code` in the query string.
 *       POST that code once to receive `access_token`, `refresh_token`, and `user`.
 *       The code expires in a few minutes and is single-use (in-memory store; use Redis in production for multiple instances).
 *     tags: [Auth]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - code
 *             properties:
 *               code:
 *                 type: string
 *                 description: One-time code from the Google success redirect.
 *     responses:
 *       200:
 *         description: Tokens issued.
 *       400:
 *         description: Invalid or expired code.
 */
router.post(
  '/oauth/exchange',
  oauthExchangeValidationRules,
  validate,
  authController.exchangeOAuthCode
);

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
 * /api/auth/register:
 *   post:
 *     summary: Register a new user
 *     description: Create a new user account with default role USER and status ACTIVE.
 *     tags: [Auth]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - full_name
 *               - email
 *               - password
 *             properties:
 *               full_name:
 *                 type: string
 *                 minLength: 2
 *                 maxLength: 100
 *                 example: New User
 *               email:
 *                 type: string
 *                 format: email
 *                 example: newuser@example.com
 *               password:
 *                 type: string
 *                 format: password
 *                 minLength: 8
 *                 example: newuser123456
 *     responses:
 *       201:
 *         description: User registered successfully.
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
 *                   example: User registered successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     user:
 *                       type: object
 *                       properties:
 *                         id:
 *                           type: string
 *                           example: 665f1a2b9c1e2a0012a12345
 *                         full_name:
 *                           type: string
 *                           example: New User
 *                         email:
 *                           type: string
 *                           example: newuser@example.com
 *                         role:
 *                           type: string
 *                           example: USER
 *                         status:
 *                           type: string
 *                           example: ACTIVE
 *       400:
 *         description: Validation failed or email already registered.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: false
 *                 message:
 *                   type: string
 *                   example: Email is already registered
 */
router.post('/register', registerValidationRules, validate, authController.register);

module.exports = router;
