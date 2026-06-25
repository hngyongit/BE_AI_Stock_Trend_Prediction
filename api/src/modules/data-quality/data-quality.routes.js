const express = require('express');
const router = express.Router();

const dataQualityController = require('./data-quality.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const roleMiddleware = require('../../common/middlewares/role.middleware');
const {
    validate,
    missingRecordsRules
} = require('./data-quality.validation');

// All routes require authentication + ADMIN or STAFF role
router.use(authMiddleware);
router.use(roleMiddleware(['ADMIN', 'STAFF']));

/**
 * @openapi
 * tags:
 *   - name: Staff Data Quality
 *     description: STAFF and ADMIN data quality monitoring (read-only)
 */

/**
 * @openapi
 * /api/staff/data-quality:
 *   get:
 *     summary: Get data quality dashboard
 *     description: Returns overall quality metrics, worst source, failed symbols count, and recent trends.
 *     tags: [Staff Data Quality]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Data quality dashboard retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/', dataQualityController.dashboard);

/**
 * @openapi
 * /api/staff/data-quality/by-source:
 *   get:
 *     summary: Get quality metrics by data source
 *     description: Returns quality metrics grouped by data source, sorted by success rate ascending.
 *     tags: [Staff Data Quality]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Quality by source retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/by-source', dataQualityController.bySource);

/**
 * @openapi
 * /api/staff/data-quality/by-job:
 *   get:
 *     summary: Get quality metrics by crawl job
 *     description: Returns quality metrics grouped by crawl job, sorted by success rate ascending.
 *     tags: [Staff Data Quality]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Quality by job retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/by-job', dataQualityController.byJob);

/**
 * @openapi
 * /api/staff/data-quality/missing:
 *   get:
 *     summary: Get missing records analysis
 *     description: Analyzes missing records within a date range. Shows total active stocks vs records inserted.
 *     tags: [Staff Data Quality]
 *     security:
 *       - bearerAuth: []
 *     parameters:
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
 *     responses:
 *       200:
 *         description: Missing records analysis retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/missing', missingRecordsRules, validate, dataQualityController.missing);

module.exports = router;