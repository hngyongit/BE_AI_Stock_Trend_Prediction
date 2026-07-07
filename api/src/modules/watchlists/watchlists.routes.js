/**
 * @openapi
 * /api/watchlists/{symbol}:
 *   delete:
 *     summary: Remove stock from personal watchlist
 *     description: Delete a stock symbol from the authorized user's watchlist. Also permanently deletes all alerts configured for this stock.
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
router.delete('/:symbol', authMiddleware, checkSubscriptionExpiry, removeWatchlistValidation, validate, watchlistsController.removeWatchlist);

/**
 * @openapi
 * /api/watchlists/trim:
 *   post:
 *     summary: Trim watchlist to specific stocks
 *     description: Remove all stocks from watchlist except those specified in keepStockIds. Used when user is over limit after subscription expiry. Also permanently deletes all alerts for removed stocks.
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
 *               - keepStockIds
 *             properties:
 *               keepStockIds:
 *                 type: array
 *                 items:
 *                   type: string
 *                 example: ["665f1a2b9c1e2a0012a99991", "665f1a2b9c1e2a0012a99992"]
 *     responses:
 *       200:
 *         description: Watchlist trimmed successfully.
 *       400:
 *         description: Validation failed or keepStockIds exceeds plan limit.
 *       401:
 *         description: Unauthorized.
 */
router.post('/trim', authMiddleware, trimWatchlistValidation, validate, watchlistsController.trimWatchlist);

module.exports = router;
