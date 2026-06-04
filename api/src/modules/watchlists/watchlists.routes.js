const express = require('express');
const router = express.Router();

const watchlistsController = require('./watchlists.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const {
  validate,
  addWatchlistValidation,
  removeWatchlistValidation
} = require('./watchlists.validation');

/**
 * @openapi
 * tags:
 *   - name: Watchlists
 *     description: User watchlist management
 */

/**
 * @openapi
 * /api/watchlists:
 *   get:
 *     summary: Retrieve personal watchlist
 *     description: Retrieve all stock symbols currently in the authorized user's watchlist with their latest close prices.
 *     tags: [Watchlists]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Watchlist retrieved successfully.
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
 *                   example: Get watchlist successfully
 *                 data:
 *                   type: array
 *                   items:
 *                     type: object
 *                     properties:
 *                       watchlist_id:
 *                         type: string
 *                         example: 665f1a2b9c1e2a0012a99991
 *                       stock:
 *                         type: object
 *                         properties:
 *                           id:
 *                             type: string
 *                             example: 665f1a2b9c1e2a0012a99999
 *                           symbol:
 *                             type: string
 *                             example: FPT
 *                           company_name:
 *                             type: string
 *                             example: Công ty Cổ phần FPT
 *                           market_id:
 *                             type: string
 *                             example: 665f1a2b9c1e2a0012a99001
 *                           market_code:
 *                             type: string
 *                             example: HOSE
 *                       latest_price:
 *                         type: object
 *                         properties:
 *                           close_price:
 *                             type: number
 *                             example: 135000
 *                           price_change:
 *                             type: number
 *                             example: 1500
 *                           price_change_percent:
 *                             type: number
 *                             example: 1.12
 *                           volume:
 *                             type: number
 *                             example: 2500000
 *                       created_at:
 *                         type: string
 *                         format: date-time
 *                         example: 2026-06-01T15:00:00.000Z
 *       401:
 *         description: Unauthorized. Missing or invalid Bearer access token.
 */
router.get('/', authMiddleware, watchlistsController.getWatchlist);

/**
 * @openapi
 * /api/watchlists:
 *   post:
 *     summary: Add stock to personal watchlist
 *     description: Add a new stock symbol to the user's watchlist. Maximum limit is 5 stocks.
 *     tags: [Watchlists]
 *     security:
 *       - bearerAuth: []
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - symbol
 *             properties:
 *               symbol:
 *                 type: string
 *                 example: FPT
 *     responses:
 *       201:
 *         description: Stock successfully added to watchlist.
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
 *                   example: Add stock to watchlist successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     watchlist_id:
 *                       type: string
 *                       example: 665f1a2b9c1e2a0012a99991
 *                     symbol:
 *                       type: string
 *                       example: FPT
 *                     created_at:
 *                       type: string
 *                       format: date-time
 *       400:
 *         description: Watchlist limit exceeded or stock is already in watchlist.
 *       401:
 *         description: Unauthorized.
 *       404:
 *         description: Stock symbol not found in system.
 */
router.post('/', authMiddleware, addWatchlistValidation, validate, watchlistsController.addWatchlist);

/**
 * @openapi
 * /api/watchlists/{symbol}:
 *   delete:
 *     summary: Remove stock from personal watchlist
 *     description: Delete a stock symbol from the authorized user's watchlist.
 *     tags: [Watchlists]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: symbol
 *         required: true
 *         schema:
 *           type: string
 *           example: FPT
 *         description: The uppercase stock symbol
 *     responses:
 *       200:
 *         description: Stock successfully removed from watchlist.
 *       401:
 *         description: Unauthorized.
 *       404:
 *         description: Stock not found in your watchlist or symbol not found.
 */
router.delete('/:symbol', authMiddleware, removeWatchlistValidation, validate, watchlistsController.removeWatchlist);

module.exports = router;
