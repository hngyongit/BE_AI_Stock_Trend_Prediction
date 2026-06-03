const mongoose = require('mongoose');

const FactMarketOverviewSchema = new mongoose.Schema(
  {
    market_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimMarket',
      required: true
    },
    time_id: {
      type: Number,
      required: true
    },
    data_source_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimDataSource',
      required: true
    },
    total_volume: {
      type: Number
    },
    total_value: {
      type: Number
    },
    total_deal_volume: {
      type: Number
    },
    total_deal_value: {
      type: Number
    },
    market_cap: {
      type: Number
    },
    number_of_stocks: {
      type: Number
    },
    listed_volume: {
      type: Number
    },
    circulating_volume: {
      type: Number
    },
    foreign_buy: {
      type: Number
    },
    foreign_sell: {
      type: Number
    },
    foreign_net: {
      type: Number
    },
    bid_volume: {
      type: Number
    },
    ask_volume: {
      type: Number
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: false
    },
    collection: 'factMarketOverviews'
  }
);

FactMarketOverviewSchema.index({ market_id: 1, time_id: 1, data_source_id: 1 }, { unique: true });

module.exports = mongoose.model('FactMarketOverview', FactMarketOverviewSchema);
