from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from vietstock_crawler.config.constants import VN_TZ
from vietstock_crawler.config.settings import (
    ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET,
    CREATE_QUARTERLY_FINANCIAL_TRADING_SHEETS,
    QUARTER_SHEET_OVERRIDE,
)

def now_vn_dt() -> datetime:
    return datetime.now(VN_TZ)


def now_vn() -> str:
    return now_vn_dt().strftime("%Y-%m-%d %H:%M:%S")


def today_suffix() -> str:
    return now_vn_dt().strftime("%d_%m_%y")


def dated_sheet_name(base_name: str) -> str:
    return f"{base_name}_{today_suffix()}"


def parse_quarter_suffix(value: Any) -> str:
    """Chuẩn hóa Q1/2026, Quý 1/2026, Q1_2026 thành Q1_2026."""
    raw = "" if value is None else str(value).strip()
    if not raw:
        return ""

    m = re.search(r"(?:Q|Quý|Qui|Quí)\s*([1-4])\s*[/_\- ]\s*(20\d{2})", raw, flags=re.IGNORECASE)
    if m:
        return f"Q{int(m.group(1))}_{int(m.group(2))}"

    m = re.search(r"\b([1-4])\s*[/_\- ]\s*(20\d{2})\b", raw)
    if m:
        return f"Q{int(m.group(1))}_{int(m.group(2))}"

    return ""


def quarter_sort_key(suffix: str) -> tuple[int, int]:
    m = re.fullmatch(r"Q([1-4])_(20\d{2})", suffix or "")
    if not m:
        return (0, 0)
    return (int(m.group(2)), int(m.group(1)))


def latest_completed_quarter_suffix(dt: Optional[datetime] = None) -> str:
    """Quý mới nhất đã kết thúc. Ví dụ tháng 05/2026 => Q1_2026."""
    dt = dt or now_vn_dt()
    current_q = ((dt.month - 1) // 3) + 1
    if current_q == 1:
        return f"Q4_{dt.year - 1}"
    return f"Q{current_q - 1}_{dt.year}"


def is_quarter_after(a: str, b: str) -> bool:
    return quarter_sort_key(a) > quarter_sort_key(b)


def clamp_reported_quarter_suffix(suffix: str) -> str:
    """Không cho sheet nhảy sang quý đang chạy dở trừ khi bật ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET."""
    suffix = parse_quarter_suffix(suffix)
    if not suffix:
        return latest_completed_quarter_suffix()
    if ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET:
        return suffix
    max_allowed = latest_completed_quarter_suffix()
    if is_quarter_after(suffix, max_allowed):
        return max_allowed
    return suffix


def quarterly_sheet_name(base_name: str, quarter_suffix: str = "") -> str:
    raw_suffix = parse_quarter_suffix(QUARTER_SHEET_OVERRIDE) or parse_quarter_suffix(quarter_suffix) or latest_completed_quarter_suffix()
    suffix = clamp_reported_quarter_suffix(raw_suffix)
    return f"{base_name}_{suffix}"


def output_sheet_name(base_name: str, quarter_suffix: str = "") -> str:
    if base_name in ["FINANCIAL_DATA", "TRADING_STATS"] and CREATE_QUARTERLY_FINANCIAL_TRADING_SHEETS:
        return quarterly_sheet_name(base_name, quarter_suffix)
    return dated_sheet_name(base_name)


def resolve_latest_reported_quarter_suffix(*record_groups: List[Dict[str, Any]]) -> str:
    """Lấy quý mới nhất từ records, nhưng mặc định không vượt quá quý đã kết thúc."""
    max_allowed = latest_completed_quarter_suffix()
    candidates: List[str] = []
    for records in record_groups:
        for record in records or []:
            for key in ["_latest_period", "bctt_latest_period"]:
                suffix = parse_quarter_suffix(record.get(key, ""))
                if not suffix:
                    continue
                if not ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET and is_quarter_after(suffix, max_allowed):
                    continue
                candidates.append(suffix)
    if not candidates:
        return max_allowed
    return max(candidates, key=quarter_sort_key)
