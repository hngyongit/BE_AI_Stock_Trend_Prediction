const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const Role = require('../models/role.model');
const User = require('../models/user.model');
const SubscriptionTransaction = require('../models/subscription-transaction.model');
const connectDB = require('../../config/database.config');
const env = require('../../config/env.config');

const seedRolesAndUsers = async () => {
  try {
    // 1. Seed Roles
    const rolesData = [
      { name: 'USER', description: 'Regular user role with basic access' },
      { name: 'STAFF', description: 'Staff role for managing crawl jobs and logs' },
      { name: 'ADMIN', description: 'Administrator role with full control' }
    ];

    const rolesMap = {};

    for (const r of rolesData) {
      let role = await Role.findOne({ name: r.name });
      if (!role) {
        role = await Role.create(r);
        console.log(`[Seed] Created role: ${r.name}`);
      } else {
        console.log(`[Seed] Role ${r.name} already exists.`);
      }
      rolesMap[r.name] = role._id;
    }

    // 2. Seed Users
    const usersData = [
      {
        full_name: 'Regular User',
        email: 'user@example.com',
        password: 'user123456',
        role: 'USER',
        status: 'ACTIVE'
      },
      {
        full_name: 'Staff Member',
        email: 'staff@example.com',
        password: 'staff123456',
        role: 'STAFF',
        status: 'ACTIVE'
      },
      {
        full_name: 'Administrator',
        email: 'admin@example.com',
        password: 'admin123456',
        role: 'ADMIN',
        status: 'ACTIVE'
      },
      {
        full_name: 'Locked User',
        email: 'locked@example.com',
        password: 'locked123456',
        role: 'USER',
        status: 'LOCKED'
      },
      {
        full_name: 'Pro User',
        email: 'pro@example.com',
        password: 'pro123456',
        role: 'USER',
        status: 'ACTIVE',
        plan: 'PRO',
        subscription_status: 'ACTIVE',
        subscription_expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000) // 30 days from now
      },
      {
        full_name: 'Expired Pro User',
        email: 'expired@example.com',
        password: 'expired123456',
        role: 'USER',
        status: 'ACTIVE',
        plan: 'PRO',
        subscription_status: 'EXPIRED',
        subscription_expires_at: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000) // 1 day ago
      }
    ];

    for (const u of usersData) {
      let user = await User.findOne({ email: u.email });
      if (!user) {
        const hashedPassword = await bcrypt.hash(u.password, env.BCRYPT_SALT_ROUNDS || 10);
        const userData = {
          full_name: u.full_name,
          email: u.email,
          password_hash: hashedPassword,
          role_id: rolesMap[u.role],
          status: u.status,
          plan: u.plan || 'FREE',
          subscription_status: u.subscription_status || 'NONE',
          subscription_expires_at: u.subscription_expires_at || null
        };
        user = await User.create(userData);
        console.log(`[Seed] Created user: ${u.email} (${u.role})`);
      } else {
        console.log(`[Seed] User ${u.email} already exists.`);
      }

      // Seed subscription transactions for PRO users
      if (u.plan === 'PRO') {
        const existingTx = await SubscriptionTransaction.findOne({ user_id: user._id });
        if (!existingTx) {
          await SubscriptionTransaction.create({
            user_id: user._id,
            transaction_type: 'PAYOS_PAYMENT',
            amount: 50000,
            status: 'PAID',
            previous_plan: 'FREE',
            new_plan: 'PRO',
            previous_expires_at: null,
            new_expires_at: u.subscription_expires_at || null,
            notes: 'Seed data: initial PRO subscription'
          });
          console.log(`[Seed] Created transaction for: ${u.email}`);
        }
      }
    }

    console.log('[Seed] Seeding completed successfully.');
  } catch (error) {
    console.error(`[Seed] Error seeding roles and users: ${error.message}`);
    throw error;
  }
};

// If run directly
if (require.main === module) {
  const runStandalone = async () => {
    await connectDB();
    await seedRolesAndUsers();
    await mongoose.connection.close();
    process.exit(0);
  };
  runStandalone();
}

module.exports = seedRolesAndUsers;
