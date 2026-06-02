from __future__ import annotations

from typing import Any, Dict

from vietstock_crawler.models.columns import MARKET_COLUMNS, FINANCIAL_COLUMNS, TRADING_STATS_COLUMNS
from vietstock_crawler.utils.date_utils import now_vn

def empty_market_record(symbol: str, source: str, error: str = "", note: str = "") -> Dict[str, Any]:
    record = {key: None for key, _ in MARKET_COLUMNS}
    record.update({"snapshot_at": now_vn(), "symbol": symbol, "source": source, "is_valid_url": False, "error": error, "note": note})
    return record


def empty_financial_record(symbol: str, source: str, error: str = "", note: str = "") -> Dict[str, Any]:
    record = {key: None for key, _ in FINANCIAL_COLUMNS}
    record.update({"snapshot_at": now_vn(), "symbol": symbol, "source": source, "is_valid_url": False, "error": error, "note": note})
    return record


def empty_trading_stats_record(symbol: str, source: str, error: str = "", note: str = "") -> Dict[str, Any]:
    record = {key: None for key, _ in TRADING_STATS_COLUMNS}
    record.update({"snapshot_at": now_vn(), "symbol": symbol, "source": source, "is_valid_url": False, "error": error, "note": note})
    return record
