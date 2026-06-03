const mongoose = require('mongoose');

const DimTimeSchema = new mongoose.Schema(
  {
    time_id: {
      type: Number,
      required: true,
      unique: true
    },
    full_date: {
      type: Date,
      required: true
    },
    day: {
      type: Number,
      required: true
    },
    month: {
      type: Number,
      required: true
    },
    quarter: {
      type: Number,
      required: true
    },
    year: {
      type: Number,
      required: true
    },
    week_of_year: {
      type: Number,
      required: true
    },
    weekday: {
      type: Number,
      required: true
    },
    is_trading_day: {
      type: Boolean,
      default: true
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: false
    },
    collection: 'dimTimes'
  }
);

module.exports = mongoose.model('DimTime', DimTimeSchema);
