const mongoose = require('mongoose');

const CrawlLogDetailSchema = new mongoose.Schema(
  {
    crawl_log_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'CrawlLog',
      required: true
    },
    stock_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimStock',
      required: false
    },
    symbol: {
      type: String,
      required: true,
      trim: true
    },
    data_type: {
      type: String,
      required: true
    },
    status: {
      type: String,
      enum: ['SUCCESS', 'FAILED', 'SKIPPED'],
      required: true
    },
    message: {
      type: String,
      default: ''
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: false
    },
    collection: 'crawlLogDetails'
  }
);

module.exports = mongoose.model('CrawlLogDetail', CrawlLogDetailSchema);
