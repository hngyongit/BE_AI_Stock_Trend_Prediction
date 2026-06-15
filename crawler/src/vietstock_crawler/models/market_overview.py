from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Market Overview field definitions
# ---------------------------------------------------------------------------
# Each entry: (field_name, description, python_type, required)
MARKET_OVERVIEW_FIELDS: List[Tuple[str, str, type, bool]] = [
    ("trading_date", "Trading date (normalized date only)", str, True),
    ("symbol", "Normalized symbol: VNINDEX, VN30, HNXINDEX, UPCOMINDEX", str, True),
    ("display_symbol", "Original display name: VN-Index, VN30, HNX-Index", str, False),
    ("market", "Market: HOSE, HNX, UPCOM, DERIVATIVE, UNKNOWN", str, False),

    ("reference_index", "Reference / tham chiếu", float, False),
    ("open_index", "Open / mở cửa", float, False),
    ("close_index", "Close / đóng cửa", float, False),
    ("high_index", "High / cao nhất", float, False),
    ("low_index", "Low / thấp nhất", float, False),

    ("change_value", "Change value / thay đổi điểm", float, False),
    ("change_percent", "Change percent / thay đổi %", float, False),

    ("matched_volume", "Matched volume / GD khớp lệnh KL", float, False),
    ("matched_value", "Matched value / GD khớp lệnh GT", float, False),

    ("put_through_volume", "Put-through volume / GD thỏa thuận KL", float, False),
    ("put_through_value", "Put-through value / GD thỏa thuận GT", float, False),

    ("total_volume", "Total volume / tổng giao dịch KL", float, False),
    ("total_value", "Total value / tổng giao dịch GT", float, False),

    ("market_cap", "Market capitalization / vốn hóa thị trường", float, False),

    ("last_trading_time", "Last trading date/time", str, False),
    ("source", "Source name: init_api, daily_table, crawler", str, False),
    ("raw_data", "Original raw payload for debugging", dict, False),
]

# Fields that must be numeric (or null)
NUMERIC_FIELDS = {
    "reference_index", "open_index", "close_index", "high_index", "low_index",
    "change_value", "change_percent",
    "matched_volume", "matched_value",
    "put_through_volume", "put_through_value",
    "total_volume", "total_value",
    "market_cap",
}


def empty_market_overview_record() -> Dict[str, Any]:
    """Create an empty MarketOverview record with all fields set to None."""
    record: Dict[str, Any] = {}
    for field_name, _, _, _ in MARKET_OVERVIEW_FIELDS:
        record[field_name] = None
    record["raw_data"] = None
    return record


def get_validation_errors(record: Dict[str, Any]) -> List[str]:
    """
    Validate a market overview record.
    Returns a list of error messages. Empty list means valid.
    """
    errors: List[str] = []

    # Required fields
    if not record.get("trading_date"):
        errors.append("trading_date is required")
    if not record.get("symbol"):
        errors.append("symbol is required")

    # Numeric fields should be numbers or None
    for field in NUMERIC_FIELDS:
        val = record.get(field)
        if val is not None:
            try:
                float(val)
            except (TypeError, ValueError):
                errors.append(f"{field} must be a number or null, got {type(val).__name__}")

    # high_index >= low_index
    high = record.get("high_index")
    low = record.get("low_index")
    if high is not None and low is not None:
        try:
            if float(high) < float(low):
                errors.append(
                    f"high_index ({high}) is less than low_index ({low})"
                )
        except (TypeError, ValueError):
            pass  # Already caught above

    return errors
