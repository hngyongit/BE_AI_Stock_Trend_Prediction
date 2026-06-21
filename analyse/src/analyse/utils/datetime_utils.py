from __future__ import annotations

from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError


def _resolve_timezone(timezone: str):
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        # Fallback to UTC to prevent runtime crashes when tz data is unavailable.
        return dt_timezone.utc


def now_iso(timezone: str = "Asia/Ho_Chi_Minh") -> str:
    return datetime.now(_resolve_timezone(timezone)).isoformat(timespec="seconds")


def timestamp_for_filename(timezone: str = "Asia/Ho_Chi_Minh") -> str:
    return datetime.now(_resolve_timezone(timezone)).strftime("%Y%m%d_%H%M%S")
