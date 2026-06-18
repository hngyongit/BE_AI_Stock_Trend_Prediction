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
    symbol: {
      type: String,
      required: true
    },
    display_symbol: {
      type: String
    },
    reference_index: {
      type: Number
    },
    open_index: {
      type: Number
    },
    close_index: {
      type: Number
    },
    high_index: {
      type: Number
    },
    low_index: {
      type: Number
    },
    change_value: {
      type: Number
    },
    change_percent: {
      type: Number
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
    },
    last_trading_time: {
      type: Date
    },
    source: {
      type: String
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

FactMarketOverviewSchema.index({ market_id: 1, time_id: 1, symbol: 1 }, { unique: true });

module.exports = mongoose.model('FactMarketOverview', FactMarketOverviewSchema);

