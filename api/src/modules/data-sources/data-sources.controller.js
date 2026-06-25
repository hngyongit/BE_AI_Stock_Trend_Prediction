const dataSourcesService = require('./data-sources.service');
const { success } = require('../../common/utils/response.util');

/**
 * Format data source object for API response
 */
const formatDataSource = (source) => ({
    id: source._id.toString(),
    name: source.name,
    provider_type: source.provider_type,
    base_url: source.base_url,
    description: source.description,
    config: source.config || {},
    status: source.status,
    created_at: source.created_at,
    updated_at: source.updated_at
});

/**
 * List data sources (paginated, filterable)
 */
const list = async (req, res, next) => {
    try {
        const result = await dataSourcesService.listDataSources(req.query);
        const formattedItems = result.items.map(formatDataSource);
        return success(res, 'Get data sources successfully', {
            items: formattedItems,
            pagination: result.pagination
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Get a single data source by ID
 */
const detail = async (req, res, next) => {
    try {
        const { id } = req.params;
        const source = await dataSourcesService.getDataSourceDetail(id);
        return success(res, 'Get data source successfully', {
            data_source: formatDataSource(source)
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Create a new data source
 */
const create = async (req, res, next) => {
    try {
        const source = await dataSourcesService.createDataSource(req.body);
        return success(res, 'Data source created successfully', {
            data_source: formatDataSource(source)
        }, 201);
    } catch (error) {
        next(error);
    }
};

/**
 * Update an existing data source
 */
const update = async (req, res, next) => {
    try {
        const { id } = req.params;
        const source = await dataSourcesService.updateDataSource(id, req.body);
        return success(res, 'Data source updated successfully', {
            data_source: formatDataSource(source)
        });
    } catch (error) {
        next(error);
    }
};

/**
 * Toggle data source status (active ↔ inactive)
 */
const toggleStatus = async (req, res, next) => {
    try {
        const { id } = req.params;
        const source = await dataSourcesService.toggleDataSourceStatus(id);
        return success(res, 'Data source status toggled successfully', {
            data_source: formatDataSource(source)
        });
    } catch (error) {
        next(error);
    }
};

module.exports = {
    list,
    detail,
    create,
    update,
    toggleStatus
};