const mongoose = require('mongoose');

const DimReportPeriodSchema = new mongoose.Schema(
  {
    fiscal_year: {
      type: Number,
      required: true
    },
    fiscal_quarter: {
      type: Number,
      required: true
    },
    period_name: {
      type: String,
      required: true,
      trim: true
    },
    period_start_date: {
      type: Date
    },
    period_end_date: {
      type: Date
    },
    is_latest: {
      type: Boolean,
      default: false
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: false
    },
    collection: 'dimReportPeriods'
  }
);

module.exports = mongoose.model('DimReportPeriod', DimReportPeriodSchema);
