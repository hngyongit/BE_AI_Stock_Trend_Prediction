const DimDataSource = require('../../database/models/dim-data-source.model');

/**
 * Staff: Get paginated list of data sources (filterable)
 */
const listDataSources = async (queries) => {
    const page = parseInt(queries.page || '1', 10);
    const limit = parseInt(queries.limit || '20', 10);
    const skip = (page - 1) * limit;

    const filter = {};

    // Keyword search (name, description, base_url)
    if (queries.keyword) {
        const searchRegex = { $regex: queries.keyword, $options: 'i' };
        filter.$or = [
            { name: searchRegex },
            { description: searchRegex },
            { base_url: searchRegex }
        ];
    }

    // Status filter
    if (queries.status) {
        filter.status = queries.status;
    }

    // Provider type filter
    if (queries.provider_type) {
        filter.provider_type = queries.provider_type;
    }

    // Sort
    const sortField = queries.sort_by || 'name';
    const sortOrder = queries.sort_order === 'desc' ? -1 : 1;

    const items = await DimDataSource.find(filter)
        .sort({ [sortField]: sortOrder })
        .skip(skip)
        .limit(limit);

    const total_items = await DimDataSource.countDocuments(filter);
    const total_pages = Math.ceil(total_items / limit);

    return {
        items,
        pagination: { page, limit, total_items, total_pages }
    };
};

/**
 * Staff: Get a single data source by ID
 */
const getDataSourceDetail = async (id) => {
    const source = await DimDataSource.findById(id);
    if (!source) {
        const error = new Error('Data source not found');
        error.statusCode = 404;
        throw error;
    }
    return source;
};

/**
 * Staff/Admin: Create a new data source
 */
const createDataSource = async (data) => {
    // Check for duplicate name
    const existing = await DimDataSource.findOne({ name: data.name });
    if (existing) {
        const error = new Error('A data source with this name already exists');
        error.statusCode = 409;
        throw error;
    }

    const source = await DimDataSource.create({
        name: data.name,
        provider_type: data.provider_type || 'crawler',
        base_url: data.base_url || '',
        description: data.description || '',
        config: data.config || {},
        status: data.status || 'active'
    });

    return source;
};

/**
 * Staff/Admin: Update an existing data source
 */
const updateDataSource = async (id, data) => {
    const source = await DimDataSource.findById(id);
    if (!source) {
        const error = new Error('Data source not found');
        error.statusCode = 404;
        throw error;
    }

    // Check for duplicate name if name is being changed
    if (data.name && data.name !== source.name) {
        const existing = await DimDataSource.findOne({ name: data.name });
        if (existing) {
            const error = new Error('A data source with this name already exists');
            error.statusCode = 409;
            throw error;
        }
    }

    // Build update fields
    const updateFields = {};
    if (data.name !== undefined) updateFields.name = data.name;
    if (data.provider_type !== undefined) updateFields.provider_type = data.provider_type;
    if (data.base_url !== undefined) updateFields.base_url = data.base_url;
    if (data.description !== undefined) updateFields.description = data.description;
    if (data.status !== undefined) updateFields.status = data.status;
    if (data.config !== undefined) updateFields.config = data.config;

    Object.assign(source, updateFields);
    await source.save();

    return source;
};

/**
 * Staff/Admin: Toggle data source status (active ↔ inactive)
 */
const toggleDataSourceStatus = async (id) => {
    const source = await DimDataSource.findById(id);
    if (!source) {
        const error = new Error('Data source not found');
        error.statusCode = 404;
        throw error;
    }

    source.status = source.status === 'active' ? 'inactive' : 'active';
    await source.save();

    return source;
};

module.exports = {
    listDataSources,
    getDataSourceDetail,
    createDataSource,
    updateDataSource,
    toggleDataSourceStatus
};