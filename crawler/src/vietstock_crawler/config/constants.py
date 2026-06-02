from __future__ import annotations

from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
BASE_FINANCE = "https://finance.vietstock.vn"

DEFAULT_CONFIG_SHEET_NAME = "CONFIG"
DEFAULT_MARKET_SHEET_BASE = "MARKET_DATA"
DEFAULT_FINANCIAL_SHEET_BASE = "FINANCIAL_DATA"
DEFAULT_TRADING_STATS_SHEET_BASE = "TRADING_STATS"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Referer": "https://finance.vietstock.vn/",
}

AD_BLOCK_KEYWORDS = [
    "doubleclick", "googlesyndication", "googleadservices", "google-analytics",
    "googletagmanager", "adservice", "adsystem", "mgid", "admicro",
    "ambient", "adnxs", "taboola", "outbrain", "criteo", "tracking",
    "analytics", "banner", "popup", "facebook", "zalo", "tiktok",
]
