const crypto = require('crypto');

const TTL_MS = 5 * 60 * 1000;
const store = new Map();

/**
 * Store one-time OAuth exchange payload (tokens + user summary).
 * @param {{ access_token: string, refresh_token: string, user: object }} payload
 * @returns {string} opaque code for POST /oauth/exchange
 */
const put = (payload) => {
  const code = crypto.randomBytes(24).toString('hex');
  store.set(code, { ...payload, expiresAt: Date.now() + TTL_MS });
  return code;
};

/**
 * Consume code once; returns payload or null if invalid/expired.
 * @param {string} code
 * @returns {{ access_token: string, refresh_token: string, user: object } | null}
 */
const take = (code) => {
  if (!code || typeof code !== 'string') return null;
  const entry = store.get(code);
  if (!entry) return null;
  store.delete(code);
  if (entry.expiresAt < Date.now()) return null;
  return {
    access_token: entry.access_token,
    refresh_token: entry.refresh_token,
    user: entry.user
  };
};

module.exports = { put, take };
