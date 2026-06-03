const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const appConfig = require('./config/app.config');
const errorMiddleware = require('./common/middlewares/error.middleware');
const authRouter = require('./modules/auth/auth.routes');
const { usersRouter, adminUsersRouter } = require('./modules/users/users.routes');
const { stocksRouter, adminStocksRouter } = require('./modules/stocks/stocks.routes');
const watchlistsRouter = require('./modules/watchlists/watchlists.routes');
const { error } = require('./common/utils/response.util');

const swaggerUi = require('swagger-ui-express');
const swaggerSpec = require('./config/swagger.config');

const app = express();

// Set security HTTP headers (disable Content Security Policy to allow Swagger UI inline assets)
app.use(helmet({
  contentSecurityPolicy: false
}));

// Enable CORS
app.use(cors(appConfig.corsOptions));

// HTTP request logging
app.use(morgan(appConfig.env === 'development' ? 'dev' : 'combined'));

// Parse JSON and urlencoded request bodies
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Swagger API Documentation
app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec));

// API Routes
app.use('/api/auth', authRouter);
app.use('/api/users', usersRouter);
app.use('/api/admin/users', adminUsersRouter);
app.use('/api/stocks', stocksRouter);
app.use('/api/admin/stocks', adminStocksRouter);
app.use('/api/watchlists', watchlistsRouter);

// Health check endpoint
app.get('/', (req, res) => {
  res.json({ message: 'AI Stock Trend Prediction API is running' });
});

// Send back a 404 error for any unknown api request
app.use((req, res, next) => {
  return error(res, `Route ${req.originalUrl} not found`, null, 404);
});

// Global error handler
app.use(errorMiddleware);

module.exports = app;
