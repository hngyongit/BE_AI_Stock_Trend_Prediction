const dataQualityService = require('./data-quality.service');
const { success } = require('../../common/utils/response.util');

/**
 * Get quality dashboard summary
 */
const dashboard = async (req, res, next) => {
    try {
        const result = await dataQualityService.getQualityDashboard();
        return success(res, 'Get data quality dashboard successfully', result);
    } catch (error) {
        next(error);
    }
};

/**
 * Get quality metrics grouped by data source
 */
const bySource = async (req, res, next) => {
    try {
        const result = await dataQualityService.getQualityBySource();
        return success(res, 'Get quality by source successfully', { items: result });
    } catch (error) {
        next(error);
    }
};

/**
 * Get quality metrics grouped by crawl job
 */
const byJob = async (req, res, next) => {
    try {
        const result = await dataQualityService.getQualityByJob();
        return success(res, 'Get quality by job successfully', { items: result });
    } catch (error) {
        next(error);
    }
};

/**
 * Get missing records analysis
 */
const missing = async (req, res, next) => {
    try {
        const result = await dataQualityService.getMissingRecords(req.query);
        return success(res, 'Get missing records analysis successfully', result);
    } catch (error) {
        next(error);
    }
};

module.exports = {
    dashboard,
    bySource,
    byJob,
    missing
};