const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

const UserSchema = new mongoose.Schema(
  {
    role_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Role',
      required: true
    },
    full_name: {
      type: String,
      required: true,
      trim: true
    },
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
      index: true
    },
    password_hash: {
      type: String,
      default: null
    },
    google_id: {
      type: String,
      sparse: true,
      unique: true,
      trim: true
    },
    status: {
      type: String,
      enum: ['ACTIVE', 'LOCKED'],
      default: 'ACTIVE'
    },
    refresh_token_hash: {
      type: String,
      default: null
    },
    last_login_at: {
      type: Date,
      default: null
    },
    plan: {
      type: String,
      enum: ['FREE', 'PRO'],
      default: 'FREE'
    },
    subscription_status: {
      type: String,
      enum: ['NONE', 'ACTIVE', 'EXPIRED', 'CANCELLED'],
      default: 'NONE'
    },
    subscription_expires_at: {
      type: Date,
      default: null
    },
    payos_order_code: {
      type: Number,
      default: null,
      sparse: true
    },
    payos_payment_link_id: {
      type: String,
      default: null,
      sparse: true
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: 'updated_at'
    }
  }
);

// Instance method to check password validity
UserSchema.methods.comparePassword = async function (candidatePassword) {
  if (!this.password_hash) return false;
  return bcrypt.compare(candidatePassword, this.password_hash);
};

// Custom serialization: strip sensitive fields on conversion to JSON
UserSchema.set('toJSON', {
  transform: (doc, ret) => {
    delete ret.password_hash;
    delete ret.refresh_token_hash;
    delete ret.__v;
    return ret;
  }
});

module.exports = mongoose.model('User', UserSchema);
