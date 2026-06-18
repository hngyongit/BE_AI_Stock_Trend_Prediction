const mongoose = require('mongoose');

const SubscriptionTransactionSchema = new mongoose.Schema(
  {
    user_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true,
      index: true
    },
    transaction_type: {
      type: String,
      enum: ['PAYOS_PAYMENT', 'ADMIN_GRANT', 'ADMIN_RENEW', 'ADMIN_CANCEL', 'ADMIN_MODIFY'],
      required: true
    },
    // PayOS fields
    payos_order_code: {
      type: Number,
      default: null,
      sparse: true
    },
    payos_payment_link_id: {
      type: String,
      default: null
    },
    amount: {
      type: Number,
      default: 0   // VND
    },
    // Trạng thái
    status: {
      type: String,
      enum: ['PAID', 'CANCELLED', 'REFUNDED', 'GRANTED', 'EXPIRED'],
      required: true
    },
    // Thông tin subscription trước và sau
    previous_plan: { type: String, enum: ['FREE', 'PRO'], default: 'FREE' },
    new_plan:      { type: String, enum: ['FREE', 'PRO'], default: 'FREE' },
    previous_expires_at: { type: Date, default: null },
    new_expires_at:      { type: Date, default: null },
    // Người thực hiện (nếu là ADMIN can thiệp)
    performed_by: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      default: null
    },
    // Ghi chú / lý do
    notes: {
      type: String,
      default: ''
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: 'updated_at'
    }
  }
);

// Index cho tra cứu nhanh
SubscriptionTransactionSchema.index({ user_id: 1, created_at: -1 });
SubscriptionTransactionSchema.index({ payos_order_code: 1 }, { sparse: true });
SubscriptionTransactionSchema.index({ status: 1 });
SubscriptionTransactionSchema.index({ created_at: -1 });

module.exports = mongoose.model('SubscriptionTransaction', SubscriptionTransactionSchema);
