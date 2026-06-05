from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from vietstock_crawler.config.constants import DEFAULT_CONFIG_SHEET_NAME


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """Typed runtime configuration loaded from `.env` and environment variables."""

    # MongoDB configurations
    mongodb_uri: str
    save_to_mongodb: bool
    load_config_from_mongodb: bool

    # Google Sheets configurations
    save_to_gsheet: bool
    google_sheet_id: str
    google_service_account_file: str
    config_sheet_name: str

    request_delay_seconds: float
    page_wait_ms: int
    page_timeout_ms: int
    symbol_crawl_timeout: float
    max_page_retries: int
    page_retry_sleep_seconds: float
    playwright_wait_until: str
    bctt_page_wait_ms: int

    gsheet_max_retries: int
    gsheet_retry_base_seconds: int
    apply_formats: bool
    format_number_columns: bool

    trading_stats_weekday: int
    trading_stats_min_daily_run: int
    force_run_trading_stats: bool
    force_refresh_trading_stats: bool

    enable_financial_data: bool
    enable_trading_stats: bool
    create_quarterly_financial_trading_sheets: bool
    use_latest_reported_quarter_for_sheets: bool
    allow_incomplete_current_quarter_sheet: bool
    quarter_sheet_override: str

    block_ads: bool
    close_popups: bool

    enable_llm: bool
    openai_api_key: Optional[str]
    openai_model: str
    dry_run: bool
    crawl_limit: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        wait_until = os.getenv("PLAYWRIGHT_WAIT_UNTIL", "domcontentloaded").strip().lower()
        if wait_until == "networkidle" or wait_until not in {"domcontentloaded", "load", "commit"}:
            wait_until = "domcontentloaded"

        return cls(
            mongodb_uri=os.getenv("MONGODB_URI", "").strip(),
            save_to_mongodb=env_bool("SAVE_TO_MONGODB", True),
            load_config_from_mongodb=env_bool("LOAD_CONFIG_FROM_MONGODB", True),
            save_to_gsheet=env_bool("SAVE_TO_GSHEET", False),
            google_sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip(),
            google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json").strip(),
            config_sheet_name=os.getenv("CONFIG_SHEET_NAME", DEFAULT_CONFIG_SHEET_NAME).strip(),
            request_delay_seconds=env_float("REQUEST_DELAY_SECONDS", 1.5),
            page_wait_ms=env_int("PAGE_WAIT_MS", 2000),
            page_timeout_ms=env_int("PAGE_TIMEOUT_MS", 60000),
            symbol_crawl_timeout=env_float("SYMBOL_CRAWL_TIMEOUT", 90.0),
            max_page_retries=env_int("MAX_PAGE_RETRIES", 2),
            page_retry_sleep_seconds=env_float("PAGE_RETRY_SLEEP_SECONDS", 5.0),
            playwright_wait_until=wait_until,
            bctt_page_wait_ms=env_int("BCTT_PAGE_WAIT_MS", 2500),
            gsheet_max_retries=env_int("GSHEET_MAX_RETRIES", 6),
            gsheet_retry_base_seconds=env_int("GSHEET_RETRY_BASE_SECONDS", 65),
            apply_formats=env_bool("APPLY_FORMATS", False),
            format_number_columns=env_bool("FORMAT_NUMBER_COLUMNS", True),
            trading_stats_weekday=env_int("TRADING_STATS_WEEKDAY", 4),
            trading_stats_min_daily_run=env_int("TRADING_STATS_MIN_DAILY_RUN", 2),
            force_run_trading_stats=env_bool("FORCE_RUN_TRADING_STATS", False),
            force_refresh_trading_stats=env_bool("FORCE_REFRESH_TRADING_STATS", False),
            enable_financial_data=env_bool("ENABLE_FINANCIAL_DATA", False),
            enable_trading_stats=env_bool("ENABLE_TRADING_STATS", False),
            create_quarterly_financial_trading_sheets=(
                env_bool("CREATE_QUARTERLY_FINANCIAL_TRADING_SHEETS", True)
                or env_bool("FINANCIAL_TRADING_SHEETS_BY_QUARTER", False)
                or env_bool("QUARTERLY_FINANCIAL_TRADING_SHEETS", False)
            ),
            use_latest_reported_quarter_for_sheets=env_bool("USE_LATEST_REPORTED_QUARTER_FOR_SHEETS", True),
            allow_incomplete_current_quarter_sheet=env_bool("ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET", False),
            quarter_sheet_override=os.getenv("QUARTER_SHEET_OVERRIDE", "").strip().upper(),
            block_ads=env_bool("BLOCK_ADS", True),
            close_popups=env_bool("CLOSE_POPUPS", True),
            enable_llm=env_bool("ENABLE_LLM", False),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5").strip(),
            dry_run=env_bool("DRY_RUN", False),
            crawl_limit=env_int("CRAWL_LIMIT", 0),
        )

    def validate_required(self) -> None:
        if self.save_to_mongodb or self.load_config_from_mongodb:
            if not self.mongodb_uri:
                raise RuntimeError("Thiếu MONGODB_URI trong file .env khi sử dụng MongoDB")
        
        if self.save_to_gsheet or not self.load_config_from_mongodb:
            if not self.google_sheet_id:
                raise RuntimeError("Thiếu GOOGLE_SHEET_ID trong file .env khi sử dụng Google Sheets")
            if not Path(self.google_service_account_file).exists():
                raise RuntimeError(f"Không tìm thấy file service account: {self.google_service_account_file} khi sử dụng Google Sheets")


SETTINGS = Settings.from_env()

# Compatibility constants used by parsing/service modules. They are centralized here.
MONGODB_URI = SETTINGS.mongodb_uri
SAVE_TO_MONGODB = SETTINGS.save_to_mongodb
LOAD_CONFIG_FROM_MONGODB = SETTINGS.load_config_from_mongodb
SAVE_TO_GSHEET = SETTINGS.save_to_gsheet

SHEET_ID = SETTINGS.google_sheet_id
SERVICE_ACCOUNT_FILE = SETTINGS.google_service_account_file
CONFIG_SHEET_NAME = SETTINGS.config_sheet_name
REQUEST_DELAY_SECONDS = SETTINGS.request_delay_seconds
PAGE_WAIT_MS = SETTINGS.page_wait_ms
PAGE_TIMEOUT_MS = SETTINGS.page_timeout_ms
SYMBOL_CRAWL_TIMEOUT = SETTINGS.symbol_crawl_timeout
MAX_PAGE_RETRIES = SETTINGS.max_page_retries
PAGE_RETRY_SLEEP_SECONDS = SETTINGS.page_retry_sleep_seconds
PLAYWRIGHT_WAIT_UNTIL = SETTINGS.playwright_wait_until
BCTT_PAGE_WAIT_MS = SETTINGS.bctt_page_wait_ms
GSHEET_MAX_RETRIES = SETTINGS.gsheet_max_retries
GSHEET_RETRY_BASE_SECONDS = SETTINGS.gsheet_retry_base_seconds
APPLY_FORMATS = SETTINGS.apply_formats
FORMAT_NUMBER_COLUMNS = SETTINGS.format_number_columns
TRADING_STATS_WEEKDAY = SETTINGS.trading_stats_weekday
TRADING_STATS_MIN_DAILY_RUN = SETTINGS.trading_stats_min_daily_run
FORCE_RUN_TRADING_STATS = SETTINGS.force_run_trading_stats
FORCE_REFRESH_TRADING_STATS = SETTINGS.force_refresh_trading_stats
ENABLE_FINANCIAL_DATA = SETTINGS.enable_financial_data
ENABLE_TRADING_STATS = SETTINGS.enable_trading_stats
CREATE_QUARTERLY_FINANCIAL_TRADING_SHEETS = SETTINGS.create_quarterly_financial_trading_sheets
USE_LATEST_REPORTED_QUARTER_FOR_SHEETS = SETTINGS.use_latest_reported_quarter_for_sheets
ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET = SETTINGS.allow_incomplete_current_quarter_sheet
QUARTER_SHEET_OVERRIDE = SETTINGS.quarter_sheet_override
BLOCK_ADS = SETTINGS.block_ads
CLOSE_POPUPS = SETTINGS.close_popups


def get_settings() -> Settings:
    return SETTINGS
