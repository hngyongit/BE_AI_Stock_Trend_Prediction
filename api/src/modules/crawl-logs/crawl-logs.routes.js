const express = require('express');
const router = express.Router();

const crawlLogsController = require('./crawl-logs.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const roleMiddleware = require('../../common/middlewares/role.middleware');

// All routes require authentication + ADMIN or STAFF role
router.use(authMiddleware);
router.use(roleMiddleware(['ADMIN', 'STAFF']));

/**
 * @openapi
 * tags:
 *   - name: Staff Crawl Logs
 *     description: STAFF and ADMIN crawl log monitoring (read-only)
 */

// Static routes MUST come before parameterized routes (/failed-symbols before /:id)

/**
 * @openapi
 * /api/staff/crawl-logs/failed-symbols:
 *   get:
 *     summary: Get all failed symbols across logs
 *     description: Returns all FAILED detail records across all crawl logs, optionally filtered by crawl_job_id.
 *     tags: [Staff Crawl Logs]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: query
 *         name: crawl_job_id
 *         schema:
 *           type: string
 *       - in: query
 *         name: limit
 *         schema:
 *           type: integer
 *     responses:
 *       200:
 *         description: Failed symbols retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/failed-symbols', crawlLogsController.allFailedSymbols);

/**
 * @openapi
 * /api/staff/crawl-logs:
 *   get:
 *     summary: List crawl logs (paginated, filterable)
 *     description: Returns paginated list of crawl execution logs. Accessible by STAFF and ADMIN.
 *     tags: [Staff Crawl Logs]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: query
 *         name: page
 *         schema:
 *           type: integer
 *           default: 1
 *       - in: query
 *         name: limit
 *         schema:
 *           type: integer
 *           default: 20
 *       - in: query
 *         name: crawl_job_id
 *         schema:
 *           type: string
 *       - in: query
 *         name: status
 *         schema:
 *           type: string
 *           enum: [PENDING, SUCCESS, FAILED, PARTIAL_SUCCESS]
 *       - in: query
 *         name: date_from
 *         schema:
 *           type: string
 *           format: date
 *       - in: query
 *         name: date_to
 *         schema:
 *           type: string
 *           format: date
 *       - in: query
 *         name: sort_by
 *         schema:
 *           type: string
 *           default: started_at
 *       - in: query
 *         name: sort_order
 *         schema:
 *           type: string
 *           enum: [asc, desc]
 *     responses:
 *       200:
 *         description: Crawl logs retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/', crawlLogsController.list);

/**
 * @openapi
 * /api/staff/crawl-logs/{id}:
 *   get:
 *     summary: Get crawl log detail with all child records
 *     description: Returns a single crawl log with all its per-symbol detail records.
 *     tags: [Staff Crawl Logs]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Crawl log retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: Crawl log not found.
 */
router.get('/:id', crawlLogsController.detail);

/**
 * @openapi
 * /api/staff/crawl-logs/{id}/failed-symbols:
 *   get:
 *     summary: Get failed symbols from a crawl log
 *     description: Returns all FAILED detail records within a specific crawl log.
 *     tags: [Staff Crawl Logs]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Failed symbols retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/:id/failed-symbols', crawlLogsController.failedSymbols);

/**
 * @openapi
 * /api/staff/crawl-logs/{id}/by-symbol:
 *   get:
 *     summary: Get details by symbol within a crawl log
 *     description: Filter crawl log details by symbol.
 *     tags: [Staff Crawl Logs]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *       - in: query
 *         name: symbol
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Details retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/:id/by-symbol', crawlLogsController.detailBySymbol);

module.exports = router;