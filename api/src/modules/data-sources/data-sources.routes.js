const express = require('express');
const router = express.Router();

const dataSourcesController = require('./data-sources.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const roleMiddleware = require('../../common/middlewares/role.middleware');
const {
    validate,
    createDataSourceRules,
    updateDataSourceRules,
    toggleStatusRules,
    listDataSourcesRules,
    getDataSourceRules
} = require('./data-sources.validation');

// All routes require authentication + ADMIN or STAFF role
router.use(authMiddleware);
router.use(roleMiddleware(['ADMIN', 'STAFF']));

/**
 * @openapi
 * tags:
 *   - name: Staff Data Sources
 *     description: STAFF and ADMIN data source management
 */

/**
 * @openapi
 * /api/staff/data-sources:
 *   get:
 *     summary: List data sources (paginated, filterable)
 *     description: Returns paginated list of data source providers. Accessible by STAFF and ADMIN.
 *     tags: [Staff Data Sources]
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
 *         name: provider_type
 *         schema:
 *           type: string
 *           enum: [crawler, api, file_import]
 *       - in: query
 *         name: keyword
 *         schema:
 *           type: string
 *         description: Search by name, description, or base_url
 *       - in: query
 *         name: sort_by
 *         schema:
 *           type: string
 *           enum: [name, provider_type, status, created_at]
 *       - in: query
 *         name: sort_order
 *         schema:
 *           type: string
 *           enum: [asc, desc]
 *     responses:
 *       200:
 *         description: Data sources retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 */
router.get('/', listDataSourcesRules, validate, dataSourcesController.list);

/**
 * @openapi
 * /api/staff/data-sources/{id}:
 *   get:
 *     summary: Get data source detail
 *     description: Returns a single data source by ID.
 *     tags: [Staff Data Sources]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *         description: Data source ID
 *     responses:
 *       200:
 *         description: Data source retrieved successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: Data source not found.
 */
router.get('/:id', getDataSourceRules, validate, dataSourcesController.detail);

/**
 * @openapi
 * /api/staff/data-sources:
 *   post:
 *     summary: Create a new data source
 *     description: Create a new data source provider registry entry.
 *     tags: [Staff Data Sources]
 *     security:
 *       - bearerAuth: []
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - name
 *             properties:
 *               name:
 *                 type: string
 *               provider_type:
 *                 type: string
 *                 enum: [crawler, api, file_import]
 *               base_url:
 *                 type: string
 *               description:
 *                 type: string
 *               status:
 *                 type: string
 *                 enum: [active, inactive]
 *     responses:
 *       201:
 *         description: Data source created successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       409:
 *         description: Duplicate name.
 */
router.post('/', createDataSourceRules, validate, dataSourcesController.create);

/**
 * @openapi
 * /api/staff/data-sources/{id}:
 *   put:
 *     summary: Update a data source
 *     description: Update an existing data source by ID.
 *     tags: [Staff Data Sources]
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
 *               name:
 *                 type: string
 *               provider_type:
 *                 type: string
 *                 enum: [crawler, api, file_import]
 *               base_url:
 *                 type: string
 *               description:
 *                 type: string
 *               status:
 *                 type: string
 *                 enum: [active, inactive]
 *     responses:
 *       200:
 *         description: Data source updated successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: Data source not found.
 */
router.put('/:id', updateDataSourceRules, validate, dataSourcesController.update);

/**
 * @openapi
 * /api/staff/data-sources/{id}/toggle-status:
 *   patch:
 *     summary: Toggle data source status
 *     description: Toggle data source between active and inactive status.
 *     tags: [Staff Data Sources]
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
 *         description: Data source status toggled successfully.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: Data source not found.
 */
router.patch('/:id/toggle-status', toggleStatusRules, validate, dataSourcesController.toggleStatus);

module.exports = router;