const DimDataSource = require('../models/dim-data-source.model');

const seedDataSources = async () => {
    try {
        const sourcesData = [
            {
                name: 'vietstock',
                provider_type: 'crawler',
                base_url: 'https://finance.vietstock.vn',
                description: 'Vietstock Finance crawler — Daily market price, financial statements, and financial report sources',
                config: {},
                status: 'active'
            }
        ];

        for (const s of sourcesData) {
            const existing = await DimDataSource.findOne({ name: s.name });
            if (!existing) {
                await DimDataSource.create(s);
                console.log(`[Seed] Created data source: ${s.name}`);
            } else {
                console.log(`[Seed] Data source ${s.name} already exists.`);
            }
        }
    } catch (error) {
        console.error(`[Seed] Error seeding data sources: ${error.message}`);
    }
};

module.exports = seedDataSources;