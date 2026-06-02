from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from vietstock_crawler.config.settings import get_settings
from vietstock_crawler.core.browser import VietstockBrowser
from vietstock_crawler.core.logging_config import configure_logging
from vietstock_crawler.models.columns import FINANCIAL_COLUMNS, MARKET_COLUMNS, TRADING_STATS_COLUMNS
from vietstock_crawler.parsers.trading_stats_parser import crawl_trading_stats
from vietstock_crawler.services.google_sheets_service import (
    append_records_with_titles,
    get_daily_run_index,
    get_gspread_client,
    read_config,
    should_run_trading_stats_today,
)
from vietstock_crawler.services.vietstock_service import crawl_company
from vietstock_crawler.utils.date_utils import (
    dated_sheet_name,
    latest_completed_quarter_suffix,
    output_sheet_name,
    parse_quarter_suffix,
    resolve_latest_reported_quarter_suffix,
)
from vietstock_crawler.utils.text_utils import clean_config_text
from vietstock_crawler.utils.url_utils import normalize_slug_value


def run() -> None:
    """Application entry point used by `run.py`."""
    configure_logging()
    settings = get_settings()
    settings.validate_required()

    client = get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheet_id)
    configs = read_config(spreadsheet)
    symbols_count = len([x for x in configs if clean_config_text(x.get("symbol"))])

    market_records: List[Dict[str, Any]] = []
    financial_records: List[Dict[str, Any]] = []
    trading_records: List[Dict[str, Any]] = []

    market_sheet_name = dated_sheet_name("MARKET_DATA")
    preliminary_quarter_suffix = parse_quarter_suffix(settings.quarter_sheet_override) or latest_completed_quarter_suffix()
    preliminary_financial_sheet_name = output_sheet_name("FINANCIAL_DATA", preliminary_quarter_suffix) if settings.enable_financial_data else ""
    preliminary_trading_sheet_name = output_sheet_name("TRADING_STATS", preliminary_quarter_suffix) if settings.enable_trading_stats else ""

    current_run_index = get_daily_run_index(spreadsheet, market_sheet_name, symbols_count)
    run_trading_stats = should_run_trading_stats_today(
        spreadsheet,
        preliminary_trading_sheet_name,
        current_run_index,
        symbols_count,
    ) if settings.enable_trading_stats else False

    logging.info("Today sheets:")
    logging.info(" - %s", market_sheet_name)
    logging.info(" - %s", preliminary_financial_sheet_name if settings.enable_financial_data else "FINANCIAL_DATA skipped: ENABLE_FINANCIAL_DATA=false")
    logging.info(" - %s", preliminary_trading_sheet_name if run_trading_stats else "TRADING_STATS skipped")
    logging.info("Daily run index: %s", current_run_index)
    logging.info("ENABLE_FINANCIAL_DATA: %s", "ON" if settings.enable_financial_data else "OFF")
    logging.info("ENABLE_TRADING_STATS: %s", "ON" if settings.enable_trading_stats else "OFF")
    logging.info("Financial/Trading quarterly sheets: %s", "ON" if settings.create_quarterly_financial_trading_sheets else "OFF")
    logging.info("Preliminary quarter suffix: %s", preliminary_quarter_suffix)
    logging.info("Number column formatting: %s", "ON" if (settings.apply_formats or settings.format_number_columns) else "OFF")

    with VietstockBrowser() as browser:
        for item in configs:
            symbol = clean_config_text(item.get("symbol")).upper()
            slug = normalize_slug_value(item.get("slug"))
            profile_url = clean_config_text(item.get("profile_url"))
            trading_stats_url = clean_config_text(item.get("trading_stats_url"))
            if not symbol:
                continue

            logging.info("Crawling %s", symbol)
            market, financial = crawl_company(
                symbol=symbol,
                slug=slug,
                browser=browser,
                profile_url=profile_url,
                crawl_financial=settings.enable_financial_data,
            )
            market_records.append(market)

            if settings.enable_financial_data:
                financial_records.append(financial)

            time.sleep(settings.request_delay_seconds)

            if settings.enable_trading_stats and run_trading_stats:
                stats = crawl_trading_stats(symbol=symbol, browser=browser, trading_stats_url=trading_stats_url)
                trading_records.append(stats)
                time.sleep(settings.request_delay_seconds)

    final_quarter_suffix = preliminary_quarter_suffix
    financial_sheet_name = preliminary_financial_sheet_name
    trading_sheet_name = preliminary_trading_sheet_name

    if settings.create_quarterly_financial_trading_sheets and (settings.enable_financial_data or (settings.enable_trading_stats and run_trading_stats)):
        if settings.use_latest_reported_quarter_for_sheets:
            final_quarter_suffix = resolve_latest_reported_quarter_suffix(financial_records, trading_records)
        financial_sheet_name = output_sheet_name("FINANCIAL_DATA", final_quarter_suffix) if settings.enable_financial_data else ""
        trading_sheet_name = output_sheet_name("TRADING_STATS", final_quarter_suffix) if settings.enable_trading_stats else ""
    elif not settings.create_quarterly_financial_trading_sheets:
        financial_sheet_name = dated_sheet_name("FINANCIAL_DATA") if settings.enable_financial_data else ""
        trading_sheet_name = dated_sheet_name("TRADING_STATS") if settings.enable_trading_stats else ""
        final_quarter_suffix = ""

    logging.info("Final output sheets:")
    logging.info(" - %s", market_sheet_name)
    logging.info(" - %s", financial_sheet_name if settings.enable_financial_data else "FINANCIAL_DATA skipped")
    logging.info(" - %s", trading_sheet_name if (settings.enable_trading_stats and run_trading_stats) else "TRADING_STATS skipped")
    if final_quarter_suffix:
        logging.info("Final quarter suffix: %s", final_quarter_suffix)

    append_records_with_titles(spreadsheet, market_sheet_name, market_records, MARKET_COLUMNS)

    if settings.enable_financial_data and financial_sheet_name and financial_records:
        append_records_with_titles(spreadsheet, financial_sheet_name, financial_records, FINANCIAL_COLUMNS)

    if settings.enable_trading_stats and run_trading_stats and trading_sheet_name and trading_records:
        append_records_with_titles(spreadsheet, trading_sheet_name, trading_records, TRADING_STATS_COLUMNS)

    logging.info(
        "Done. Sheets: %s, %s, %s. Rows: MARKET=%s, FINANCIAL=%s, TRADING_STATS=%s",
        market_sheet_name,
        financial_sheet_name if settings.enable_financial_data else "SKIPPED",
        trading_sheet_name if (settings.enable_trading_stats and run_trading_stats) else "SKIPPED",
        len(market_records),
        len(financial_records),
        len(trading_records),
    )
