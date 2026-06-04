const mongoose = require('mongoose');

const CrawlJobSchema = new mongoose.Schema(
  {
    data_source_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimStockDataSource',
      required: true
    },
    market_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimMarket',
      required: true
    },
    job_name: {
      type: String,
      required: true,
      trim: true
    },
    data_type: {
      type: String,
      enum: ['DAILY_MARKET_PRICE', 'QUARTERLY_FINANCIAL_STATEMENT', 'FINANCIAL_REPORT_SOURCE'],
      required: true
    },
    cron_expression: {
      type: String,
      required: true,
      trim: true
    },
    crawl_mode: {
      type: String,
      enum: ['scheduled', 'manual'],
      default: 'scheduled'
    },
    status: {
      type: String,
      enum: ['active', 'inactive'],
      default: 'active'
    },
    last_run_at: {
      type: Date
    },
    next_run_at: {
      type: Date
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: 'updated_at'
    },
    collection: 'crawlJobs'
  }
);

module.exports = mongoose.model('CrawlJob', CrawlJobSchema);
