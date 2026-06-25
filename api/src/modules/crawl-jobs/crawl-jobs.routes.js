const express = require('express');
const router = express.Router();

const crawlJobsController = require('./crawl-jobs.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const roleMiddleware = require('../../common/middlewares/role.middleware');
const {
    validate,
    createCrawlJobRules,
    updateCrawlJobRules,
    toggleStatusRules,
    listCrawlJobsRules,
    getCrawlJobRules
} = require('./crawl-jobs.validation');

// All routes require authentication + ADMIN or STAFF role
router.use(authMiddleware);
router.use(roleMiddleware(['ADMIN', 'STAFF']));

/**
 * @openapi
 * tags:
 *   - name: Staff Crawl Jobs
 *     description: STAFF and ADMIN crawl job configuration
 */

/**
 * @openapi
 * /api/staff/crawl-jobs:
 *   get:
 *     summary: List crawl jobs (paginated, filterable)
 *     description: Returns paginated list of crawl job configurations. Accessible by STAFF and ADMIN.
 *     tags: [Staff Crawl Jobs]
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
 *         name: status
 *         schema:
 *           type: string
 *           enum: [active, inactive]
 *       - in: query
 *         name: data_type
 *         schema:
 *           type: string
 *           enum: [DAILY_MARKET_PRICE, QUARTERLY_FINANCIAL_STATEMENT, FINANCIAL_REPORT_SOURCE, MARKET_OVERVIEW]
 *       - in: query
 *         name: data_source_id
 *         schema:
 *           type: string
 *       - in: query
 *         name: market_id
 *         schema:
 *           type: string
 *       - in: query
 *         name: keyword
 *         schema:
 *           type: string
 *       - in: query
 *         name: sort_by
 *         schema:
 *           type: string
 *           enum: [job_name, data_type, status, created_at, next_run_at]
 *       - in: query
 *         name: sort_order
 *         schema:
 *           type: string
 *           enum: [asc, desc]
 *     responses:
 *       200:
 *         description: Crawl jobs retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/', listCrawlJobsRules, validate, crawlJobsController.list);

/**
 * @openapi
 * /api/staff/crawl-jobs/{id}:
 *   get:
 *     summary: Get crawl job detail
 *     description: Returns a single crawl job by ID.
 *     tags: [Staff Crawl Jobs]
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
 *         description: Crawl job retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: Crawl job not found.
 */
router.get('/:id', getCrawlJobRules, validate, crawlJobsController.detail);

/**
 * @openapi
 * /api/staff/crawl-jobs:
 *   post:
 *     summary: Create a new crawl job
 *     description: Create a new crawl job configuration. Does NOT trigger execution.
 *     tags: [Staff Crawl Jobs]
 *     security:
 *       - bearerAuth: []
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - job_name
 *               - data_source_id
 *               - market_id
 *               - data_type
 *               - cron_expression
 *             properties:
 *               job_name:
 *                 type: string
 *               data_source_id:
 *                 type: string
 *               market_id:
 *                 type: string
 *               data_type:
 *                 type: string
 *                 enum: [DAILY_MARKET_PRICE, QUARTERLY_FINANCIAL_STATEMENT, FINANCIAL_REPORT_SOURCE, MARKET_OVERVIEW]
 *               cron_expression:
 *                 type: string
 *               crawl_mode:
 *                 type: string
 *                 enum: [scheduled, manual]
 *               status:
 *                 type: string
 *                 enum: [active, inactive]
 *     responses:
 *       201:
 *         description: Crawl job created successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.post('/', createCrawlJobRules, validate, crawlJobsController.create);

/**
 * @openapi
 * /api/staff/crawl-jobs/{id}:
 *   put:
 *     summary: Update a crawl job
 *     description: Update an existing crawl job configuration.
 *     tags: [Staff Crawl Jobs]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *     requestBody:
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               job_name:
 *                 type: string
 *               data_source_id:
 *                 type: string
 *               market_id:
 *                 type: string
 *               data_type:
 *                 type: string
 *                 enum: [DAILY_MARKET_PRICE, QUARTERLY_FINANCIAL_STATEMENT, FINANCIAL_REPORT_SOURCE, MARKET_OVERVIEW]
 *               cron_expression:
 *                 type: string
 *               crawl_mode:
 *                 type: string
 *                 enum: [scheduled, manual]
 *               status:
 *                 type: string
 *                 enum: [active, inactive]
 *     responses:
 *       200:
 *         description: Crawl job updated successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: Crawl job not found.
 */
router.put('/:id', updateCrawlJobRules, validate, crawlJobsController.update);

/**
 * @openapi
 * /api/staff/crawl-jobs/{id}/toggle-status:
 *   patch:
 *     summary: Toggle crawl job status
 *     description: Toggle crawl job between active and inactive status. When deactivated, next_run_at is cleared.
 *     tags: [Staff Crawl Jobs]
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
 *         description: Crawl job status toggled successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: Crawl job not found.
 */
router.patch('/:id/toggle-status', toggleStatusRules, validate, crawlJobsController.toggleStatus);

module.exports = router;