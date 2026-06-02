from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

from vietstock_crawler.config.settings import (
    APPLY_FORMATS,
    CONFIG_SHEET_NAME,
    FORCE_REFRESH_TRADING_STATS,
    FORCE_RUN_TRADING_STATS,
    FORMAT_NUMBER_COLUMNS,
    GSHEET_MAX_RETRIES,
    GSHEET_RETRY_BASE_SECONDS,
    SERVICE_ACCOUNT_FILE,
    TRADING_STATS_MIN_DAILY_RUN,
    TRADING_STATS_WEEKDAY,
)
from vietstock_crawler.models.columns import DECIMAL_FIELDS, INTEGER_FIELDS, LARGE_FINANCIAL_FIELDS
from vietstock_crawler.utils.date_utils import now_vn_dt
from vietstock_crawler.utils.text_utils import clean_cell_value, clean_config_text
from vietstock_crawler.utils.url_utils import make_stats_url, normalize_slug_value, safe_profile_url_from_config

def is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "quota exceeded" in text or "write requests per minute" in text


def gsheet_call(fn, *args, **kwargs):
    last_exc = None
    for attempt in range(GSHEET_MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            last_exc = e
            if not is_quota_error(e) or attempt >= GSHEET_MAX_RETRIES:
                raise
            wait_seconds = GSHEET_RETRY_BASE_SECONDS + attempt * 10
            logging.warning("Google Sheets quota 429. Đợi %s giây rồi retry %s/%s...", wait_seconds, attempt + 1, GSHEET_MAX_RETRIES)
            time.sleep(wait_seconds)
    if last_exc:
        raise last_exc
    return None


def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return gspread.authorize(creds)


def get_or_create_worksheet(spreadsheet, title: str, rows: int = 5000, cols: int = 120):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def get_existing_data_row_count(spreadsheet, title: str) -> int:
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return 0
    values = ws.get_all_values()
    return max(0, len(values) - 1) if values else 0


def get_daily_run_index(spreadsheet, market_sheet_name: str, symbols_count: int) -> int:
    if symbols_count <= 0:
        return 1
    existing_rows = get_existing_data_row_count(spreadsheet, market_sheet_name)
    return existing_rows // symbols_count + 1


def should_run_trading_stats_today(spreadsheet, trading_sheet_name: str, current_run_index: int, symbols_count: int) -> bool:
    """
    Logic mặc định:
    - Chỉ chạy TRADING_STATS vào thứ 6.
    - Từ lần chạy thứ 2 trong ngày trở đi.
    - Nếu sheet đã đủ số dòng bằng số mã thì skip để tránh duplicate.

    Có thể ép chạy lại bằng .env:
    FORCE_RUN_TRADING_STATS=true
    FORCE_REFRESH_TRADING_STATS=true
    """
    now = now_vn_dt()

    if not FORCE_RUN_TRADING_STATS:
        if now.weekday() != TRADING_STATS_WEEKDAY:
            logging.info("Skip TRADING_STATS: weekday=%s, chỉ chạy weekday=%s.", now.weekday(), TRADING_STATS_WEEKDAY)
            return False
        if current_run_index < TRADING_STATS_MIN_DAILY_RUN:
            logging.info("Skip TRADING_STATS: daily run index=%s, cần >=%s.", current_run_index, TRADING_STATS_MIN_DAILY_RUN)
            return False

    existing_stats_rows = get_existing_data_row_count(spreadsheet, trading_sheet_name)
    if existing_stats_rows > 0 and not FORCE_REFRESH_TRADING_STATS:
        if symbols_count > 0 and existing_stats_rows >= symbols_count:
            logging.info(
                "Skip TRADING_STATS: sheet %s đã có %s dòng, đủ >= số mã %s. Muốn chạy lại đặt FORCE_REFRESH_TRADING_STATS=true.",
                trading_sheet_name,
                existing_stats_rows,
                symbols_count,
            )
            return False
        logging.info(
            "TRADING_STATS sheet %s mới có %s/%s dòng, sẽ crawl tiếp vì dữ liệu chưa đủ.",
            trading_sheet_name,
            existing_stats_rows,
            symbols_count,
        )

    if FORCE_RUN_TRADING_STATS:
        logging.info("Enable TRADING_STATS: FORCE_RUN_TRADING_STATS=true.")
    else:
        logging.info("Enable TRADING_STATS: thứ 6 và daily run index=%s.", current_run_index)
    return True


def column_letter(index_1_based: int) -> str:
    result = ""
    n = index_1_based
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def format_header(ws):
    # Luôn tô header/title xanh nhạt + chữ đậm, không phụ thuộc APPLY_FORMATS.
    try:
        gsheet_call(ws.freeze, rows=1)
        gsheet_call(ws.format, "1:1", {
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
            "backgroundColor": {"red": 0.90, "green": 0.95, "blue": 1.00},
        })
    except Exception:
        pass


def apply_number_formats(ws, columns: List[tuple]):
    # Format số độc lập với APPLY_FORMATS để tránh sheet hiển thị thành một dãy số dài.
    # Locale Việt Nam sẽ hiển thị 4.829.457; Locale United States sẽ hiển thị 4,829,457.
    if not (APPLY_FORMATS or FORMAT_NUMBER_COLUMNS):
        return
    try:
        requests = []
        for idx, (key, _) in enumerate(columns, start=1):
            col = column_letter(idx)
            if key in INTEGER_FIELDS or key in LARGE_FINANCIAL_FIELDS:
                requests.append({"range": f"{col}:{col}", "format": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}})
            elif key in DECIMAL_FIELDS:
                requests.append({"range": f"{col}:{col}", "format": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}})
        if requests and hasattr(ws, "batch_format"):
            gsheet_call(ws.batch_format, requests)
        else:
            for req in requests:
                gsheet_call(ws.format, req["range"], req["format"])
        format_header(ws)
    except Exception as e:
        logging.warning("Format worksheet failed: %s", e)


def append_records_with_titles(spreadsheet, sheet_name: str, records: List[Dict[str, Any]], columns: List[tuple]):
    if not records:
        return
    ws = get_or_create_worksheet(spreadsheet, sheet_name, rows=max(5000, len(records) + 10), cols=max(120, len(columns) + 5))
    keys = [item[0] for item in columns]
    titles = [item[1] for item in columns]
    existing = ws.get_all_values()
    rows = [[clean_cell_value(record.get(key, "")) for key in keys] for record in records]

    if not existing:
        gsheet_call(ws.update, [titles] + rows, value_input_option="USER_ENTERED")
        apply_number_formats(ws, columns)
        return
    if existing[0][:len(titles)] != titles:
        gsheet_call(ws.update, "1:1", [titles], value_input_option="USER_ENTERED")
        format_header(ws)
    gsheet_call(ws.append_rows, rows, value_input_option="USER_ENTERED")
    apply_number_formats(ws, columns)


def read_config(spreadsheet) -> List[Dict[str, str]]:
    ws = get_or_create_worksheet(spreadsheet, CONFIG_SHEET_NAME, rows=1000, cols=10)
    rows = ws.get_all_records()
    if not rows:
        gsheet_call(ws.update, [["symbol", "slug", "company_name_vi", "profile_url", "trading_stats_url"]], value_input_option="USER_ENTERED")
        raise RuntimeError("Sheet CONFIG đang trống. Hãy điền ít nhất 2 cột: symbol, slug rồi chạy lại.")

    configs = []
    seen = set()
    for row in rows:
        symbol = clean_config_text(row.get("symbol")).upper()
        slug = normalize_slug_value(row.get("slug"))
        company_name_vi = clean_config_text(row.get("company_name_vi"))
        profile_url_raw = clean_config_text(row.get("profile_url"))
        trading_stats_url_raw = clean_config_text(row.get("trading_stats_url"))

        # MARKET_DATA/FINANCIAL_DATA chỉ được dùng profile chính.
        # Nếu profile_url bị điền nhầm trang thống kê thì bỏ qua để dùng slug.
        profile_url = safe_profile_url_from_config(profile_url_raw)
        trading_stats_url = trading_stats_url_raw if "thong-ke-giao-dich" in trading_stats_url_raw.lower() else make_stats_url(symbol)

        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        configs.append({
            "symbol": symbol,
            "slug": slug,
            "company_name_vi": company_name_vi,
            "profile_url": profile_url,
            "trading_stats_url": trading_stats_url,
        })
    if not configs:
        raise RuntimeError("Không đọc được mã nào từ CONFIG. Kiểm tra lại cột symbol/slug.")
    return configs
