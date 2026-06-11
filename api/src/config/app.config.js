const env = require("./env.config");

/** Reflect request Origin when unset (works with credentials); else whitelist from CORS_ORIGINS. */
const corsOrigin =
  env.CORS_ORIGINS && env.CORS_ORIGINS.length > 0 ? env.CORS_ORIGINS : true;

module.exports = {
  port: env.PORT || 5000,
  env: env.NODE_ENV,
  isProduction: env.NODE_ENV === "production",
  sessionSecret: env.SESSION_SECRET,
  corsOptions: {
    origin: corsOrigin,
    methods: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"],
    credentials: true,
  },
};
