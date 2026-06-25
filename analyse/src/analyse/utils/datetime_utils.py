from __future__ import annotations

from datetime import datetime
from datetime import timezone as dt_timezone
from email.utils import parsedate_to_datetime
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


def format_datetime_vi(value: object, include_time: bool = True, timezone: str = "Asia/Ho_Chi_Minh") -> str:
    """Format ngày/giờ cho báo cáo người đọc, tránh hiển thị ISO raw."""

    parsed = _parse_datetime(value)
    if parsed is None:
        return "Chưa xác minh"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    local_dt = parsed.astimezone(_resolve_timezone(timezone))
    has_time = _value_has_time(value)
    if include_time and has_time:
        return local_dt.strftime("%d/%m/%Y %H:%M")
    return local_dt.strftime("%d/%m/%Y")


def format_percent_ratio(value: object, decimals: int = 0) -> str:
    """Format confidence/probability-like values for reader-facing reports."""

    if value is None or value == "":
        return "Chưa xác minh"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if numeric != numeric:  # NaN guard
        return "Chưa xác minh"
    percent = numeric * 100 if 0 <= numeric <= 1 else numeric
    if decimals <= 0:
        return f"{round(percent):.0f}%"
    return f"{percent:.{decimals}f}%"


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None

    iso_text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_text)
    except ValueError:
        pass

    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None


def _value_has_time(value: object) -> bool:
    if isinstance(value, datetime):
        return True
    text = str(value or "")
    return "T" in text or ":" in text
