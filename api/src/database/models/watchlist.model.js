const mongoose = require('mongoose');

const WatchlistSchema = new mongoose.Schema(
  {
    user_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true
    },
    stock_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimStock',
      required: true
    },
    created_at: {
      type: Date,
      default: Date.now
    }
  }
);

WatchlistSchema.index({ user_id: 1, stock_id: 1 }, { unique: true });

module.exports = mongoose.model('Watchlist', WatchlistSchema);
