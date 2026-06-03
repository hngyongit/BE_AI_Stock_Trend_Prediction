const mongoose = require('mongoose');

const FactCrawlQualitySchema = new mongoose.Schema(
  {
    crawl_job_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'CrawlJob',
      required: false
    },
    data_source_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimDataSource',
      required: true
    },
    market_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimMarket',
      required: false
    },
    time_id: {
      type: Number,
      required: true
    },
    records_fetched: {
      type: Number,
      required: true,
      default: 0
    },
    records_inserted: {
      type: Number,
      required: true,
      default: 0
    },
    records_updated: {
      type: Number,
      required: true,
      default: 0
    },
    records_failed: {
      type: Number,
      required: true,
      default: 0
    },
    success_rate: {
      type: Number,
      required: true,
      default: 0.0
    },
    status: {
      type: String,
      enum: ['SUCCESS', 'FAILED', 'PARTIAL_SUCCESS'],
      required: true
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: false
    },
    collection: 'factCrawlQualities'
  }
);

module.exports = mongoose.model('FactCrawlQuality', FactCrawlQualitySchema);
