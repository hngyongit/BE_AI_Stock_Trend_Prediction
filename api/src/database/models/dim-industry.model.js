const mongoose = require('mongoose');

const DimIndustrySchema = new mongoose.Schema(
  {
    industry_name: {
      type: String,
      required: true,
      trim: true
    },
    sector_name: {
      type: String,
      trim: true,
      default: ''
    },
    description: {
      type: String,
      default: ''
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: 'updated_at'
    },
    collection: 'dimIndustries'
  }
);

module.exports = mongoose.model('DimIndustry', DimIndustrySchema);
