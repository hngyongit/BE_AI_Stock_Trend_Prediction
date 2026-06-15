# Configuration

All supported environment variables are loaded in `src/vietstock_crawler/config/settings.py`.

Important keys:

- `GOOGLE_SHEET_ID`: target Google Sheet ID.
- `GOOGLE_SERVICE_ACCOUNT_FILE`: local path to service account JSON.
- `CONFIG_SHEET_NAME`: usually `CONFIG`.
- `ENABLE_FINANCIAL_DATA`: whether to parse profile financial metrics and BCTT fallback.
- `ENABLE_TRADING_STATS`: whether to parse trading statistics.
- `FORCE_RUN_TRADING_STATS`: bypass weekday/run-index rules.
- `FORCE_REFRESH_TRADING_STATS`: crawl trading stats even if the sheet already looks complete.
- `CREATE_QUARTERLY_FINANCIAL_TRADING_SHEETS`: write financial/trading outputs to quarterly sheets.
- `USE_LATEST_REPORTED_QUARTER_FOR_SHEETS`: resolve sheet suffix from parsed latest BCTT period.
- `ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET`: allow current unfinished quarter as output suffix.
- `QUARTER_SHEET_OVERRIDE`: manual quarter suffix such as `Q1_2026`.
- `ENABLE_LLM`: optional future LLM layer; disabled by default.
- `ENABLE_DAILY_MARKET_OVERVIEW` (default `true`): sau khi crawl giá (daily), chạy thêm một lần crawler KQGD / thống kê giá (Playwright) và ghi `market_overviews` trên MongoDB. Tắt bằng `false` nếu chỉ muốn chạy tay hoặc tách job riêng.

Never commit `.env`.
