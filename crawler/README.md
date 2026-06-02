# llm-vietstock-data-crawler

A folder-based Python 3.11+ project for crawling public Vietstock Finance pages and writing Vietnamese stock market data to Google Sheets. The project preserves the original crawler behavior while making the codebase easier to maintain, test, and extend with optional LLM-assisted checks.

## Features

- Crawls Vietstock company profile pages for `MARKET_DATA_dd_mm_yy`.
- Optionally crawls financial metrics into `FINANCIAL_DATA_Qx_yyyy`.
- Optionally crawls trading statistics into `TRADING_STATS_Qx_yyyy`.
- Optionally crawls the BCTT tab and merges latest reported BCTT values into trading statistics.
- Preserves URL validation, wrong-page detection, error-page detection, retry behavior, direct requests fallback, ad blocking, popup handling, and Google Sheets formatting.
- Keeps sensitive values in `.env`; no secrets are hard-coded.
- Provides optional LLM hooks that are disabled by default.

## Folder structure

```txt
llm-vietstock-data-crawler/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── run.py
├── src/vietstock_crawler/
│   ├── config/      # settings and constants
│   ├── core/        # browser, logging, exceptions
│   ├── models/      # output columns and empty record factories
│   ├── parsers/     # shared parser helpers and domain parsers
│   ├── services/    # Vietstock, Google Sheets, optional LLM services
│   ├── utils/       # date, number, text, URL helpers
│   └── app.py       # orchestration
├── tests/
└── docs/
```

## Installation

Windows PowerShell:

```powershell
cd llm-vietstock-data-crawler
python -m venv .venv
.\.venv\Scriptsctivate
pip install -r requirements.txt
playwright install chromium
```

## `.env` setup

Copy `.env.example` to `.env` and fill in your own values:

```powershell
Copy-Item .env.example .env
notepad .env
```

Do not commit `.env` or your service account JSON file.

## Google service account setup

1. Create a Google Cloud service account.
2. Download its JSON credential file.
3. Put the file in the project root, usually as `service_account.json`.
4. Share your target Google Sheet with the service account `client_email` as Viewer/Editor.
5. Put the spreadsheet ID in `.env` as `GOOGLE_SHEET_ID`.

## Google Sheets CONFIG sheet format

The project expects a `CONFIG` worksheet with these columns:

```txt
symbol | slug | company_name_vi | profile_url | trading_stats_url
```

`profile_url` and `trading_stats_url` are backward-compatible optional helpers. `slug` should be the company profile slug, not a trading stats or financial tab URL.

## Run

```powershell
python run.py
```

## Output sheets

- `MARKET_DATA_dd_mm_yy`
- `FINANCIAL_DATA_Qx_yyyy`
- `TRADING_STATS_Qx_yyyy`

Quarterly financial/trading sheet names are controlled by:

```env
CREATE_QUARTERLY_FINANCIAL_TRADING_SHEETS=true
USE_LATEST_REPORTED_QUARTER_FOR_SHEETS=true
ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET=false
QUARTER_SHEET_OVERRIDE=
```

## Troubleshooting

### Missing service account file

Check `GOOGLE_SERVICE_ACCOUNT_FILE` in `.env` and confirm the file exists in the project root.

### Invalid Vietstock slug

The crawler rejects auxiliary URLs such as `thong-ke-giao-dich`, `tai-chinh`, or `ket-qua-kinh-doanh` when they are used as a company profile URL.

### Google Sheets quota 429

The Google Sheets service uses quota retry. Increase these if needed:

```env
GSHEET_MAX_RETRIES=6
GSHEET_RETRY_BASE_SECONDS=65
```

### Playwright timeout

The browser retries page loads and falls back to direct `requests` where possible. You can tune:

```env
PAGE_TIMEOUT_MS=25000
MAX_PAGE_RETRIES=5
PAGE_RETRY_SLEEP_SECONDS=5
```

### Wrong page loaded

The crawler detects when a trading statistics page is accidentally used as a company profile page and records a clear error instead of parsing wrong values.

### Empty price or suspicious price

Price extraction is intentionally conservative. If the parsed price is outside the high/low sanity range, the crawler clears it and writes a note instead of storing a misleading value.
