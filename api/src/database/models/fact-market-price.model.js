const mongoose = require('mongoose');

const FactMarketPriceSchema = new mongoose.Schema(
  {
    stock_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimStock',
      required: true
    },
    market_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimMarket',
      required: true
    },
    industry_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimIndustry',
      required: true
    },
    data_source_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimDataSource',
      required: true
    },
    time_id: {
      type: Number,
      required: true
    },

    // Giá OHLCV
    open_price: {
      type: Number,
      required: true
    },
    high_price: {
      type: Number,
      required: true
    },
    low_price: {
      type: Number,
      required: true
    },
    close_price: {
      type: Number,
      required: true
    },
    volume: {
      type: Number,
      required: true
    },

    // Khối lượng đặt mua/bán
    bid_volume: {
      type: Number,
      default: null
    },
    ask_volume: {
      type: Number,
      default: null
    },

    // Giao dịch khối ngoại
    foreign_buy: {
      type: Number,
      default: null
    },
    foreign_sell: {
      type: Number,
      default: null
    },
    foreign_net: {
      type: Number,
      default: null
    },

    // Vốn hóa thị trường
    market_cap: {
      type: Number,
      default: null
    },

    // Chỉ số định giá & tài chính
    eps: {
      type: Number,
      default: null
    },
    pe: {
      type: Number,
      default: null
    },
    forward_pe: {
      type: Number,
      default: null
    },
    bvps: {
      type: Number,
      default: null
    },
    pb: {
      type: Number,
      default: null
    },
    beta: {
      type: Number,
      default: null
    },
    ros: {
      type: Number,
      default: null
    },
    roe: {
      type: Number,
      default: null
    },
    roaa: {
      type: Number,
      default: null
    },

    // Biến động giá
    price_change: {
      type: Number,
      default: null
    },
    price_change_percent: {
      type: Number,
      default: null
    },

    // Metadata
    crawled_at: {
      type: Date,
      default: Date.now
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: false
    },
    collection: 'factMarketPrices'
  }
);

// Unique constraint: mỗi mã cổ phiếu chỉ có 1 record mỗi ngày cho mỗi nguồn dữ liệu
FactMarketPriceSchema.index({ stock_id: 1, time_id: 1, data_source_id: 1 }, { unique: true });

module.exports = mongoose.model('FactMarketPrice', FactMarketPriceSchema);
