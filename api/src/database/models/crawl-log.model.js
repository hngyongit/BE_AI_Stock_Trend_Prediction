const mongoose = require('mongoose');

const CrawlLogSchema = new mongoose.Schema(
  {
    crawl_job_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'CrawlJob',
      required: false
    },
    started_at: {
      type: Date,
      required: true,
      default: Date.now
    },
    ended_at: {
      type: Date
    },
    status: {
      type: String,
      enum: ['PENDING', 'SUCCESS', 'FAILED', 'PARTIAL_SUCCESS'],
      default: 'PENDING'
    },
    records_fetched: {
      type: Number,
      default: 0
    },
    records_inserted: {
      type: Number,
      default: 0
    },
    records_updated: {
      type: Number,
      default: 0
    },
    records_failed: {
      type: Number,
      default: 0
    },
    error_message: {
      type: String,
      default: ''
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: false
    },
    collection: 'crawlLogs'
  }
);

module.exports = mongoose.model('CrawlLog', CrawlLogSchema);
