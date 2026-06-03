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
      required: true
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
