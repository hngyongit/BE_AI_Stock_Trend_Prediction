const env = require('./env.config');

module.exports = {
  port: env.PORT || 5000,
  env: env.NODE_ENV,
  corsOptions: {
    origin: '*',
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
    credentials: true
  }
};
