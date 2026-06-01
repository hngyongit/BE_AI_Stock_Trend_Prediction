const swaggerJSDoc = require("swagger-jsdoc");
const path = require("path");

const swaggerDefinition = {
  openapi: "3.0.0",
  info: {
    title: "AI Stock Trend Prediction API",
    version: "1.0.0",
    description:
      "API documentation for the AI Stock Trend Prediction platform backend.",
  },
  servers: [
    {
      url: "http://localhost:5000",
      description: "Development server",
    },
  ],
  components: {
    securitySchemes: {
      bearerAuth: {
        type: "http",
        scheme: "bearer",
        bearerFormat: "JWT",
        description:
          "Input your JWT Access Token in the format: Bearer <token>",
      },
    },
  },
};

const toPosixPath = (targetPath) => targetPath.replace(/\\/g, "/");

const apiGlobs = [
  toPosixPath(path.resolve(__dirname, "../modules/**/*.routes.js")),
  toPosixPath(path.resolve(__dirname, "../modules/**/*.js")),
  toPosixPath(path.resolve(__dirname, "../app.js")),
];

const options = {
  definition: swaggerDefinition,
  apis: apiGlobs,
};

const swaggerSpec = swaggerJSDoc(options);

module.exports = swaggerSpec;
