# Architecture

The project is organized around separation of responsibilities.

- `config/`: environment configuration and immutable constants.
- `core/`: infrastructure concerns such as Playwright browser lifecycle, logging, and custom exceptions.
- `models/`: Google Sheets output schemas and empty record factories.
- `utils/`: reusable low-level helpers for dates, text normalization, number parsing, and URL building.
- `parsers/`: HTML and text parsing rules for Vietstock pages.
- `services/`: external integration workflows for Vietstock crawling, Google Sheets output, and optional LLM extensions.
- `app.py`: orchestration layer.

The original single-file business logic was preserved but split by responsibility. The application still performs the same high-level flow: read CONFIG, crawl each symbol, collect records, resolve output sheet names, then append rows to Google Sheets.
