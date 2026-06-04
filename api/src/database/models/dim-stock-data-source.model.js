const mongoose = require('mongoose');

const DimStockDataSourceSchema = new mongoose.Schema(
  {
    stock_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimStock',
      required: true,
      unique: true
    },
    trade_stats_url: {
      type: String,
      trim: true,
      default: ''
    },
    market_price_data_url: {
      type: String,
      trim: true,
      default: ''
    },
    financial_data_url: {
      type: String,
      trim: true,
      default: ''
    },
    description: {
      type: String,
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
    collection: 'dimStockDataSources'
  }
);

module.exports = mongoose.model('DimStockDataSource', DimStockDataSourceSchema);
