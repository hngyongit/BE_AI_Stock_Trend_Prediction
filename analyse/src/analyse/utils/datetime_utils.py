from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def now_iso(timezone: str = "Asia/Ho_Chi_Minh") -> str:
    return datetime.now(ZoneInfo(timezone)).isoformat(timespec="seconds")


def timestamp_for_filename(timezone: str = "Asia/Ho_Chi_Minh") -> str:
    return datetime.now(ZoneInfo(timezone)).strftime("%Y%m%d_%H%M%S")
