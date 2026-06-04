const mongoose = require('mongoose');

const DimStockSchema = new mongoose.Schema(
  {
    market_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimMarket',
      required: true
    },
    industry_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimIndustry',
      required: false
    },
    symbol: {
      type: String,
      required: true,
      unique: true,
      uppercase: true,
      trim: true
    },
    company_name: {
      type: String,
      required: true,
      trim: true
    },
    status: {
      type: String,
      enum: ['ACTIVE', 'DELISTED', 'SUSPENDED'],
      default: 'ACTIVE'
    },
    listed_date: {
      type: Date
    },
    slug: {
      type: String,
      trim: true
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: 'updated_at'
    }
  }
);

DimStockSchema.index({ market_id: 1, symbol: 1 }, { unique: true });

module.exports = mongoose.model('DimStock', DimStockSchema);
