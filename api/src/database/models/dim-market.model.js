const mongoose = require('mongoose');

const DimMarketSchema = new mongoose.Schema(
  {
    code: {
      type: String,
      required: true,
      unique: true,
      uppercase: true,
      trim: true
    },
    name: {
      type: String,
      required: true,
      trim: true
    },
    country: {
      type: String,
      trim: true,
      default: ''
    },
    timezone: {
      type: String,
      trim: true,
      default: ''
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
    collection: 'dimMarkets'
  }
);

module.exports = mongoose.model('DimMarket', DimMarketSchema);
