const mongoose = require('mongoose');

const DimDataSourceSchema = new mongoose.Schema(
    {
        name: {
            type: String,
            required: true,
            unique: true,
            trim: true
        },
        provider_type: {
            type: String,
            enum: ['crawler', 'api', 'file_import'],
            default: 'crawler'
        },
        base_url: {
            type: String,
            trim: true,
            default: ''
        },
        description: {
            type: String,
            default: ''
        },
        config: {
            type: mongoose.Schema.Types.Mixed,
            default: {}
        },
        status: {
            type: String,
            enum: ['active', 'inactive'],
            default: 'active'
        }
    },
    {
        timestamps: {
            createdAt: 'created_at',
            updatedAt: 'updated_at'
        },
        collection: 'dimDataSources'
    }
);

module.exports = mongoose.model('DimDataSource', DimDataSourceSchema);