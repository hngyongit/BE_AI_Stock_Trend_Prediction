from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from vietstock_crawler.config.constants import BASE_FINANCE
from vietstock_crawler.utils.text_utils import clean_config_text, normalize_text

def normalize_slug_value(value: Any) -> str:
    slug = clean_config_text(value)
    if not slug:
        return ""
    slug = slug.replace(BASE_FINANCE + "/", "")
    slug = slug.replace("https://finance.vietstock.vn/", "")
    slug = slug.replace("http://finance.vietstock.vn/", "")
    slug = slug.replace(".htm", "")
    return slug.strip("/")


def make_company_url(symbol: str, slug: str, profile_url: str = "") -> str:
    symbol = clean_config_text(symbol).upper()
    profile_url = safe_profile_url_from_config(profile_url)
    if profile_url:
        return profile_url
    slug = normalize_slug_value(slug)
    if not slug:
        raise ValueError(f"Thiếu slug/profile_url hợp lệ cho mã {symbol}")
    lower_slug = slug.lower()
    if any(part in lower_slug for part in ["thong-ke-giao-dich", "tai-chinh", "ket-qua-kinh-doanh"]):
        raise ValueError(f"Slug của {symbol} đang là link phụ, không phải slug profile: {slug}")
    return f"{BASE_FINANCE}/{slug}.htm"


def make_stats_url(symbol: str, trading_stats_url: str = "") -> str:
    trading_stats_url = clean_config_text(trading_stats_url)
    if trading_stats_url.startswith("http"):
        return trading_stats_url
    return f"{BASE_FINANCE}/{symbol.strip().upper()}/thong-ke-giao-dich.htm"


def make_bctt_url(symbol: str, bctt_url: str = "") -> str:
    bctt_url = clean_config_text(bctt_url)
    if bctt_url.startswith("http"):
        return bctt_url
    return f"{BASE_FINANCE}/{symbol.strip().upper()}/tai-chinh.htm?tab=BCTT"


def normalize_url_for_compare(url: str) -> str:
    """Chuẩn hóa URL để phát hiện Playwright đang giữ lại trang cũ sau timeout."""
    url = clean_config_text(url).lower()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        query = parsed.query.lower()
        if "tab=bctt" in query:
            return f"{parsed.netloc}{path}?tab=bctt"
        return f"{parsed.netloc}{path}"
    except Exception:
        return url.split("#")[0].rstrip("/")


def is_same_navigation_target(current_url: str, target_url: str) -> bool:
    current = normalize_url_for_compare(current_url)
    target = normalize_url_for_compare(target_url)
    if not current or not target:
        return False
    if "/error/" in current or "error/index" in current:
        return True
    return current == target


def is_wrong_profile_html(html: str, symbol: str) -> bool:
    """Phát hiện MARKET/FINANCIAL lỡ lấy nhầm trang thống kê giao dịch."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title")
        title_text = title.get_text(" ", strip=True) if title else ""
        return "thong ke giao dich co phieu" in normalize_text(title_text)
    except Exception:
        return False


def is_valid_company_profile_url(url: str) -> bool:
    url = clean_config_text(url)
    lower = url.lower()
    if not lower.startswith("http") or "finance.vietstock.vn" not in lower:
        return False
    bad_parts = ["thong-ke-giao-dich", "tai-chinh", "ket-qua-kinh-doanh", "/error/", "xep-hang", "ho-so", "tin-tuc"]
    return not any(part in lower for part in bad_parts)


def safe_profile_url_from_config(profile_url: str) -> str:
    profile_url = clean_config_text(profile_url)
    return profile_url if is_valid_company_profile_url(profile_url) else ""
