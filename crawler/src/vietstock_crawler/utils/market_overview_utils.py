"""Market Overview normalization helpers.

Provides functions to parse raw API payloads and daily table data
into normalized MarketOverview records ready for MongoDB upsert.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from vietstock_crawler.config.constants import VN_TZ
from vietstock_crawler.models.market_overview import (
    MARKET_OVERVIEW_FIELDS,
    NUMERIC_FIELDS,
    empty_market_overview_record,
    get_validation_errors,
)
from vietstock_crawler.utils.number_utils import normalize_number

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Market symbol normalization map
# ---------------------------------------------------------------------------
SYMBOL_NORMALIZATION_MAP: Dict[str, str] = {
    "vn-index": "VNINDEX",
    "vnindex": "VNINDEX",
    "vn-index ": "VNINDEX",
    "vn30": "VN30",
    "vn30 ": "VN30",
    "hnx-index": "HNXINDEX",
    "hnxindex": "HNXINDEX",
    "hnx": "HNXINDEX",
    "hnx-index ": "HNXINDEX",
    "upcom": "UPCOMINDEX",
    "upcom-index": "UPCOMINDEX",
    "upcomindex": "UPCOMINDEX",
    "upcom ": "UPCOMINDEX",
}

MARKET_FROM_SYMBOL: Dict[str, str] = {
    "VNINDEX": "HOSE",
    "VN30": "HOSE",
    "HNXINDEX": "HNX",
    "UPCOMINDEX": "UPCOM",
}


# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

def parse_microsoft_date(value: Any) -> Optional[datetime]:
    """Parse Microsoft JSON date format: \"/Date(1749488400000)/\" -> datetime."""
    if value is None:
        return None
    s = str(value).strip()
    m = re.search(r"/Date\((\d+)\)/", s)
    if m:
        try:
            ms = int(m.group(1))
            return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        except (ValueError, OSError):
            return None
    return None


def parse_vietnamese_date(value: Any) -> Optional[datetime]:
    """Parse Vietnamese date format: \"11/06/2026\" -> datetime."""
    if value is None:
        return None
    s = str(value).strip()
    # Try dd/mm/yyyy
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(year, month, day, tzinfo=timezone.utc)
        except (ValueError, OSError):
            pass
    # Try yyyy-mm-dd
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except (ValueError, OSError):
            pass
    return None


def normalize_date_only(dt: Optional[datetime]) -> Optional[datetime]:
    """Zero out time components to keep only the date."""
    if dt is None:
        return None
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Number parsing
# ---------------------------------------------------------------------------

def parse_number(value: Any) -> Optional[float]:
    """Parse a value into float or None.

    Handles:
      - Formatted strings: \"1,803.71\" -> 1803.71
      - \"376,827,746\" -> 376827746
      - \"-0.28\" -> -0.28
      - Empty, null, NaN -> None
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            f = float(value)
            if f != f:  # NaN check
                return None
            return f
        except (ValueError, TypeError):
            return None
    # String path
    result = normalize_number(value)
    return result


# ---------------------------------------------------------------------------
# Symbol / market helpers
# ---------------------------------------------------------------------------

def normalize_market_symbol(value: Any) -> str:
    """Normalize a display symbol to uppercase canonical form.

    Examples:
      \"VN-Index\" -> \"VNINDEX\"
      \"VNINDEX\"  -> \"VNINDEX\"
      \"VN30\"     -> \"VN30\"
      \"HNX-Index\" -> \"HNXINDEX\"
      \"UPCOM\"    -> \"UPCOMINDEX\"
    """
    if value is None:
        return ""
    raw = str(value).strip().lower()
    # Exact or prefix match against the map
    if raw in SYMBOL_NORMALIZATION_MAP:
        return SYMBOL_NORMALIZATION_MAP[raw]
    # Try stripping trailing whitespace / dash
    candidate = raw.strip("- ").strip()
    if candidate in SYMBOL_NORMALIZATION_MAP:
        return SYMBOL_NORMALIZATION_MAP[candidate]
    # Fallback: uppercase whatever was given
    return str(value).strip().upper()


def detect_market_from_symbol(symbol: str) -> str:
    """Detect the market exchange from a normalized symbol.

    Returns one of: HOSE, HNX, UPCOM, DERIVATIVE, UNKNOWN.
    """
    return MARKET_FROM_SYMBOL.get(symbol.upper(), "UNKNOWN")


# ---------------------------------------------------------------------------
# Main normalization entry point
# ---------------------------------------------------------------------------

def normalize_market_overview(raw: Any, source: str) -> Optional[Dict[str, Any]]:
    """Normalize a raw market overview payload into a validated record dict.

    Supports two input shapes:
      1. Raw API JSON with fields like OpenIndex, CloseIndex, TradingDate, etc.
      2. Dict with Vietnamese keys like Mã CK, Mở cửa, Đóng cửa, etc.

    Returns a validated dict ready for MongoDB upsert, or None if the record
    is invalid (missing required fields or failed high >= low check).
    """
    if raw is None or not isinstance(raw, dict):
        logger.warning("normalize_market_overview: raw data is None or not a dict")
        return None

    record = empty_market_overview_record()

    # Detect payload type and normalize
    if _is_api_payload(raw):
        _normalize_api_payload(raw, record)
    else:
        _normalize_table_payload(raw, record)

    # Apply source
    record["source"] = source

    # ── Post-processing ────────────────────────────────────────────────
    # Normalize trading_date to date-only
    td = record.get("trading_date")
    if isinstance(td, datetime):
        record["trading_date"] = normalize_date_only(td)

    # Normalize symbol
    symbol = record.get("symbol") or ""
    if symbol:
        normalized = normalize_market_symbol(symbol)
        record["symbol"] = normalized
        if not record.get("market"):
            record["market"] = detect_market_from_symbol(normalized)

    # Ensure all numeric fields are float or None
    for field in NUMERIC_FIELDS:
        val = record.get(field)
        if val is not None:
            try:
                record[field] = float(val)
            except (TypeError, ValueError):
                record[field] = None

    # Save raw data for debugging
    record["raw_data"] = _sanitize_raw(raw)

    # ── Validation ─────────────────────────────────────────────────────
    errors = get_validation_errors(record)
    if errors:
        for err in errors:
            logger.warning(f"MarketOverview validation skipped: {err}")
        if "trading_date is required" in errors or "symbol is required" in errors:
            return None
        # For high < low, log warning but return None to skip
        if any("high_index" in e and "low_index" in e for e in errors):
            logger.warning(
                f"Skipping record due to high_index < low_index: "
                f"{record.get('symbol')} @ {record.get('trading_date')}"
            )
            return None

    return record


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_api_payload(raw: Dict[str, Any]) -> bool:
    """Heuristic: check for keys like OpenIndex, CloseIndex, TradingDate."""
    api_keys = {"OpenIndex", "CloseIndex", "TradingDate", "IntDateTime"}
    return bool(api_keys & set(raw.keys()))


def _normalize_api_payload(raw: Dict[str, Any], record: Dict[str, Any]) -> None:
    """Map raw API JSON fields -> normalized record."""
    # Symbol (caller should provide, but accept from raw too)
    symbol_raw = raw.get("symbol") or raw.get("Symbol") or ""
    if symbol_raw:
        record["display_symbol"] = str(symbol_raw).strip()
        record["symbol"] = normalize_market_symbol(symbol_raw)

    # Dates
    td = parse_microsoft_date(raw.get("TradingDate"))
    if td:
        record["trading_date"] = td
    ltt = parse_microsoft_date(raw.get("LastTradingDate"))
    if ltt:
        record["last_trading_time"] = ltt

    # Numeric fields
    _map_num(raw, "OpenIndex", record, "open_index")
    _map_num(raw, "HighestIndex", record, "high_index")
    _map_num(raw, "LowestIndex", record, "low_index")
    _map_num(raw, "CloseIndex", record, "close_index")
    _map_num(raw, "Change", record, "change_value")
    _map_num(raw, "PerChange", record, "change_percent")
    _map_num(raw, "TotalVol", record, "total_volume")
    _map_num(raw, "TotalVal", record, "total_value")


def _normalize_table_payload(raw: Dict[str, Any], record: Dict[str, Any]) -> None:
    """Map Vietnamese daily table keys -> normalized record."""
    # Symbol
    symbol_raw = raw.get("Mã CK") or raw.get("Ma CK") or raw.get("symbol") or ""
    if symbol_raw:
        record["display_symbol"] = str(symbol_raw).strip()
        record["symbol"] = normalize_market_symbol(symbol_raw)
        if not record.get("market"):
            record["market"] = detect_market_from_symbol(record["symbol"])

    # Date
    date_raw = raw.get("Ngày") or raw.get("TradingDate") or raw.get("trading_date")
    dt = parse_vietnamese_date(date_raw)
    if dt:
        record["trading_date"] = dt

    # Field mapping: Vietnamese label -> normalized field
    field_map: Dict[str, str] = {
        "Tham chiếu": "reference_index",
        "Mở cửa": "open_index",
        "Đóng cửa": "close_index",
        "Cao nhất": "high_index",
        "Thấp nhất": "low_index",
        "Thay đổi +/-": "change_value",
        "Thay đổi %": "change_percent",
        "GD khớp lệnh KL": "matched_volume",
        "GD khớp lệnh GT": "matched_value",
        "GD thỏa thuận KL": "put_through_volume",
        "GD thỏa thuận GT": "put_through_value",
        "Tổng giao dịch KL": "total_volume",
        "Tổng giao dịch GT": "total_value",
        "Vốn hóa thị trường": "market_cap",
    }

    for vn_label, field_name in field_map.items():
        raw_val = raw.get(vn_label)
        if raw_val is not None:
            record[field_name] = parse_number(raw_val)

    # Also handle direct English field names (already normalized)
    for field_name, _, _, _ in MARKET_OVERVIEW_FIELDS:
        if field_name in ("raw_data", "source"):
            continue
        if record.get(field_name) is None and field_name in raw:
            record[field_name] = raw[field_name]


def _map_num(
    raw: Dict[str, Any],
    raw_key: str,
    record: Dict[str, Any],
    record_key: str,
) -> None:
    """Parse a numeric value from raw and store in record."""
    val = raw.get(raw_key)
    if val is not None:
        record[record_key] = parse_number(val)


def _sanitize_raw(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return a sanitized copy safe for MongoDB storage."""
    safe: Dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, (str, int, float, bool, list, dict)):
            safe[k] = v
        else:
            safe[k] = str(v) if v is not None else None
    return safe


def normalize_kqgd_playwright_row(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map output of `scripts/market_overview_crawler.normalize_row` -> MongoDB market_overviews shape.

    The Playwright crawler uses *price* field names (open_price, close_price, …) for one table row;
    MongoDB uses the shared overview schema (*_index* names + ``symbol``).
    """
    if raw is None or not isinstance(raw, dict):
        logger.warning("normalize_kqgd_playwright_row: raw is not a dict")
        return None

    td = raw.get("trading_date")
    if not td:
        logger.warning("normalize_kqgd_playwright_row: missing trading_date")
        return None

    stock_code = raw.get("stock_code") or raw.get("StockCode") or ""
    if not str(stock_code).strip():
        logger.warning("normalize_kqgd_playwright_row: missing stock_code")
        return None

    record = empty_market_overview_record()
    try:
        from datetime import datetime
        record["trading_date"] = datetime.strptime(str(td).strip()[:10], "%Y-%m-%d")
    except Exception:
        record["trading_date"] = str(td).strip()[:10]
    record["display_symbol"] = str(raw.get("stock_name") or stock_code).strip()
    record["symbol"] = normalize_market_symbol(stock_code)
    if not record["symbol"]:
        record["symbol"] = str(stock_code).strip().upper()
    record["market"] = detect_market_from_symbol(record["symbol"])

    field_map = [
        ("reference_price", "reference_index"),
        ("open_price", "open_index"),
        ("close_price", "close_index"),
        ("highest_price", "high_index"),
        ("lowest_price", "low_index"),
        ("price_change", "change_value"),
        ("price_change_percent", "change_percent"),
        ("matched_volume", "matched_volume"),
        ("matched_value", "matched_value"),
        ("put_through_volume", "put_through_volume"),
        ("put_through_value", "put_through_value"),
        ("total_volume", "total_volume"),
        ("total_value", "total_value"),
        ("market_cap", "market_cap"),
    ]
    for src, dst in field_map:
        record[dst] = parse_number(raw.get(src))

    record["source"] = raw.get("source") or "vietstock_playwright"
    record["raw_data"] = _sanitize_raw(raw)

    for field in NUMERIC_FIELDS:
        val = record.get(field)
        if val is not None:
            try:
                record[field] = float(val)
            except (TypeError, ValueError):
                record[field] = None

    errors = get_validation_errors(record)
    if errors:
        for err in errors:
            logger.warning("normalize_kqgd_playwright_row: %s", err)
        if "trading_date is required" in errors or "symbol is required" in errors:
            return None
        if any("high_index" in e and "low_index" in e for e in errors):
            logger.warning(
                "normalize_kqgd_playwright_row: skip high < low: %s @ %s",
                record.get("symbol"),
                record.get("trading_date"),
            )
            return None

    return record
