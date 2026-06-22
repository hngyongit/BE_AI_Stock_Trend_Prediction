from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from email.utils import parsedate_to_datetime
import re
from typing import Iterable
from urllib.parse import urlparse

from analyse.schemas.research import ResearchItem


POSITIVE_KEYWORDS = (
    "tăng trưởng",
    "lãi",
    "lợi nhuận tăng",
    "cổ tức",
    "mua ròng",
    "nâng khuyến nghị",
    "vượt kế hoạch",
    "ký hợp đồng",
    "mở rộng",
    "phục hồi",
)

NEGATIVE_KEYWORDS = (
    "lỗ",
    "giảm lợi nhuận",
    "nợ",
    "xử phạt",
    "bán ròng",
    "hạ khuyến nghị",
    "cảnh báo",
    "điều tra",
    "rủi ro",
    "suy giảm",
)

CATALYST_KEYWORDS = (
    "cổ tức",
    "chia thưởng",
    "phát hành",
    "niêm yết",
    "m&a",
    "hợp đồng",
    "dự án",
    "tăng vốn",
    "kết quả kinh doanh",
    "đại hội cổ đông",
)


class BaseResearchAdapter(ABC):
    source_name: str

    @abstractmethod
    async def search(self, symbol: str, company: str | None = None) -> list[ResearchItem]:
        raise NotImplementedError


def normalize_domain(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc.lower().removeprefix("www.")


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = re.sub(r"\s+", " ", without_tags).strip()
    return normalized or None


def parse_datetime_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value.strip() or None
    if parsed.tzinfo is None:
        return parsed.isoformat(timespec="seconds")
    return parsed.isoformat(timespec="seconds")


def parse_datetime_for_sort(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


def keyword_flags(text: str | None, keywords: Iterable[str]) -> list[str]:
    normalized = (text or "").lower()
    return [keyword for keyword in keywords if keyword.lower() in normalized]


def infer_tone(positive_flags: list[str], negative_flags: list[str]) -> str:
    if positive_flags and negative_flags:
        return "hỗn hợp"
    if positive_flags:
        return "tích cực"
    if negative_flags:
        return "tiêu cực"
    return "trung tính"
