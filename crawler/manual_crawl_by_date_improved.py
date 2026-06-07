"""
manual_crawl_by_date_improved.py
--------------------------------
Script crawl thủ công dữ liệu chứng khoán theo ngày bất kỳ, cải tiến theo hướng:
- Multi-source provider/fallback.
- Không ép insert nếu thiếu field bắt buộc.
- Ghi data_completeness, missing_fields, source_used để kiểm soát chất lượng dữ liệu.
- Với dữ liệu quá khứ, vẫn cố fill foreign/bid/ask nếu nguồn có hỗ trợ.
- Tự động click "Xem thêm" để tải thêm dữ liệu lịch sử.

Cách dùng:
    python manual_crawl_by_date_improved.py --date 2026-05-22
    python manual_crawl_by_date_improved.py --date 2026-05-22 --delay 0.3 --dry-run
    python manual_crawl_by_date_improved.py --date 2026-05-22 --providers vietstock,fiintrade,eodhd
    python manual_crawl_by_date_improved.py --date 2026-05-22 --max-load-more 10 --load-more-timeout 5 --debug-provider

ENV cần có:
    MONGODB_URI=...
    MONGODB_DB_NAME=...                 # tùy chọn
    ENABLE_FINANCIAL_DATA=false         # tùy chọn

ENV cho provider fallback, nếu có license/API:
    FIINTRADE_API_URL=...
    FIINTRADE_API_KEY=...
    VIETSTOCK_DATAFEED_API_URL=...
    VIETSTOCK_DATAFEED_API_KEY=...
    EODHD_API_KEY=...
"""

from __future__ import annotations

import concurrent.futures
import argparse
import io
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import requests
from bs4 import BeautifulSoup
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

# Setup path to import vietstock_crawler
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vietstock_crawler.config.settings import get_settings
from vietstock_crawler.core.browser import VietstockBrowser
from vietstock_crawler.services.vietstock_service import crawl_company

# ─────────────────────────────────────────────
# Fix Unicode / emoji cho Windows terminal
# ─────────────────────────────────────────────
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
DATA_SOURCE_NAME = "vietstock"
DATA_SOURCE_PROVIDER_TYPE = "multi_source_crawler"
DATA_SOURCE_DESCRIPTION = "Manual crawler có multi-source fallback cho dữ liệu chứng khoán"

COL_DIM_STOCKS = "dimstocks"
COL_DIM_TIMES = "dimTimes"
COL_DIM_DATA_SOURCES = "dimDataSources"
COL_DIM_STOCK_DATA_SOURCES = "dimStockDataSources"
COL_DIM_MARKETS = "dimMarkets"
COL_FACT_MARKET_PRICES = "factMarketPrices"
COL_CRAWL_LOGS = "crawlLogs"
COL_CRAWL_LOG_DETAILS = "crawlLogDetails"
COL_FACT_CRAWL_QUALITIES = "factCrawlQualities"

REQUIRED_FIELDS = [
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "price_change",
    "price_change_percent",
]

IMPORTANT_OPTIONAL_FIELDS = [
    "bid_volume",
    "ask_volume",
    "foreign_buy",
    "foreign_sell",
    "foreign_net",
    "market_cap",
    "eps",
    "pe",
    "forward_pe",
    "bvps",
    "pb",
    "beta",
    "ros",
    "roe",
    "roaa",
]

ALL_QUALITY_FIELDS = REQUIRED_FIELDS + IMPORTANT_OPTIONAL_FIELDS


# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════
def utcnow() -> datetime:
    return datetime.utcnow()


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return False


def clean_float(value: Any) -> float | None:
    if is_empty(value):
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
        return float(value)
    except Exception:
        return None


def clean_int(value: Any) -> int | None:
    num = clean_float(value)
    if num is None:
        return None
    return int(num)


def merge_missing_fields(base: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    """Chỉ fill field còn thiếu, không ghi đè field đã có giá trị."""
    if not incoming:
        return base
    for key, value in incoming.items():
        if key in {"source_used", "provider_errors"}:
            continue
        # Cho phép ghi đè volume = 0 bằng giá trị thực > 0 từ nguồn khác
        if key == "volume" and base.get(key) == 0 and not is_empty(value) and value > 0:
            base[key] = value
        elif is_empty(base.get(key)) and not is_empty(value):
            base[key] = value
    return base


def get_missing_fields(data: dict[str, Any], fields: list[str]) -> list[str]:
    return [field for field in fields if is_empty(data.get(field))]


def is_complete_required(data: dict[str, Any]) -> bool:
    return len(get_missing_fields(data, REQUIRED_FIELDS)) == 0


def calculate_data_completeness(data: dict[str, Any]) -> float:
    filled = sum(1 for field in ALL_QUALITY_FIELDS if not is_empty(data.get(field)))
    return round(filled / len(ALL_QUALITY_FIELDS) * 100, 2)


def normalize_price_data(data: dict[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa type cho các trường numeric chính."""
    float_fields = [
        "open_price", "high_price", "low_price", "close_price",
        "price_change", "price_change_percent", "market_cap",
        "eps", "pe", "forward_pe", "bvps", "pb", "beta", "ros", "roe", "roaa",
    ]
    int_fields = ["volume", "bid_volume", "ask_volume", "foreign_buy", "foreign_sell", "foreign_net"]

    for field in float_fields:
        if field in data:
            data[field] = clean_float(data.get(field))
    for field in int_fields:
        if field in data:
            data[field] = clean_int(data.get(field))

    if is_empty(data.get("price_change")) and not is_empty(data.get("close_price")) and not is_empty(data.get("reference")):
        data["price_change"] = round(float(data["close_price"]) - float(data["reference"]), 4)

    if is_empty(data.get("price_change_percent")) and not is_empty(data.get("price_change")) and not is_empty(data.get("reference")) and float(data["reference"]) != 0:
        data["price_change_percent"] = round(float(data["price_change"]) / float(data["reference"]) * 100, 4)

    return data


# ═══════════════════════════════════════════════════════
# MongoDB
# ═══════════════════════════════════════════════════════
def connect_mongodb():
    load_dotenv()
    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        logger.error("Không tìm thấy MONGODB_URI trong file .env")
        sys.exit(1)

    db_name = os.getenv("MONGODB_DB_NAME")
    try:
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=10_000)
        client.admin.command("ping")
        db = client[db_name] if db_name else client.get_default_database()
        logger.info(f"✅ Kết nối MongoDB thành công. Database: {db.name}")
        return client, db
    except Exception as e:
        logger.error(f"❌ Không thể kết nối MongoDB: {e}")
        sys.exit(1)


def parse_date(date_str: str) -> date:
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
        logger.info(f"📅 Ngày crawl: {parsed.strftime('%d/%m/%Y')}")
        return parsed
    except ValueError:
        logger.error(f"❌ Định dạng ngày không hợp lệ: '{date_str}'. Vui lòng dùng YYYY-MM-DD.")
        sys.exit(1)


def date_to_time_id(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def get_active_hose_stocks(db) -> list[dict[str, Any]]:
    hose_market = db[COL_DIM_MARKETS].find_one({"code": {"$in": ["HOSE", "hose"]}})
    if not hose_market:
        logger.error("❌ Không tìm thấy HOSE market trong dimMarkets")
        return []

    query = {"market_id": hose_market["_id"], "status": {"$in": ["ACTIVE", "active"]}}
    projection = {"_id": 1, "symbol": 1, "market_id": 1, "industry_id": 1, "slug": 1}
    stocks = list(db[COL_DIM_STOCKS].find(query, projection).sort("symbol", 1))
    logger.info(f"📊 Tìm thấy {len(stocks)} mã cổ phiếu HOSE đang hoạt động")
    return stocks


def get_or_create_dim_time(db, target_date: date) -> int:
    col = db[COL_DIM_TIMES]
    time_id = date_to_time_id(target_date)
    existing = col.find_one({"time_id": time_id})
    if existing:
        logger.info(f"📆 dim_time đã tồn tại: time_id={time_id}")
        return time_id

    doc = {
        "time_id": time_id,
        "full_date": datetime(target_date.year, target_date.month, target_date.day),
        "day": target_date.day,
        "month": target_date.month,
        "quarter": (target_date.month - 1) // 3 + 1,
        "year": target_date.year,
        "week_of_year": target_date.isocalendar()[1],
        "weekday": target_date.weekday(),
        "is_trading_day": target_date.weekday() < 5,
        "created_at": utcnow(),
    }
    try:
        col.insert_one(doc)
        logger.info(f"📆 Đã tạo dim_time mới: time_id={time_id}")
    except Exception as exc:
        logger.warning(f"⚠️ Không tạo được dim_time hoặc đã tồn tại: {exc}")
    return time_id


def get_or_create_data_source(db, source_name: str = DATA_SOURCE_NAME) -> ObjectId:
    col = db[COL_DIM_DATA_SOURCES]
    existing = col.find_one({"name": source_name})
    if existing:
        return existing["_id"]

    doc = {
        "name": source_name,
        "provider_type": DATA_SOURCE_PROVIDER_TYPE,
        "base_url": "multi-source",
        "description": DATA_SOURCE_DESCRIPTION,
        "status": "active",
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    result = col.insert_one(doc)
    logger.info(f"🔌 Đã tạo data source mới: '{source_name}' ({result.inserted_id})")
    return result.inserted_id


def get_or_create_stock_data_source(db, stock: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    stock_id = stock["_id"]
    symbol = stock.get("symbol", "").upper()
    ds_col = db[COL_DIM_STOCK_DATA_SOURCES]
    ds = ds_col.find_one({"stock_id": stock_id})
    if ds:
        return ds

    symbol_lower = symbol.lower()
    new_ds = {
        "stock_id": stock_id,
        "trade_stats_url": f"https://finance.vietstock.vn/{symbol_lower}/thong-ke-giao-dich.htm",
        "market_price_data_url": f"https://finance.vietstock.vn/{symbol_lower}-profile.htm",
        "financial_data_url": f"https://finance.vietstock.vn/{symbol_lower}-profile.htm",
        "description": f"Vietstock crawl URLs for {symbol}",
        "status": "active",
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    if dry_run:
        new_ds["_id"] = ObjectId()
    else:
        result = ds_col.insert_one(new_ds)
        new_ds["_id"] = result.inserted_id
    logger.info(f"  [{symbol}] 🔌 Tự động tạo dimStockDataSources")
    return new_ds


# ═══════════════════════════════════════════════════════
# Crawl logs
# ═══════════════════════════════════════════════════════
def create_crawl_log(db, time_id: int) -> ObjectId:
    doc = {
        "crawl_job_id": None,
        "started_at": utcnow(),
        "ended_at": None,
        "status": "PENDING",
        "records_fetched": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "records_failed": 0,
        "error_message": f"Manual crawl cho ngày time_id={time_id}",
        "created_at": utcnow(),
    }
    result = db[COL_CRAWL_LOGS].insert_one(doc)
    return result.inserted_id


def write_crawl_log_detail(db, crawl_log_id: ObjectId, stock_id: ObjectId, symbol: str, status: str, message: str = "", data_type: str = "market_price"):
    doc = {
        "crawl_log_id": crawl_log_id,
        "stock_id": stock_id,
        "symbol": symbol,
        "data_type": data_type,
        "status": status,
        "message": message[:1000],
        "created_at": utcnow(),
    }
    db[COL_CRAWL_LOG_DETAILS].insert_one(doc)


def finalize_crawl_log(db, crawl_log_id: ObjectId, records_fetched: int, records_inserted: int, records_updated: int, records_failed: int, records_skipped: int, status: str):
    db[COL_CRAWL_LOGS].update_one(
        {"_id": crawl_log_id},
        {"$set": {
            "ended_at": utcnow(),
            "status": status,
            "records_fetched": records_fetched,
            "records_inserted": records_inserted,
            "records_updated": records_updated,
            "records_failed": records_failed,
            "error_message": f"Skipped: {records_skipped} mã không có/thiếu dữ liệu bắt buộc",
        }},
    )


def write_fact_crawl_quality(db, data_source_id: ObjectId, market_id: ObjectId | None, time_id: int, records_fetched: int, records_inserted: int, records_updated: int, records_failed: int, status: str):
    total_processed = records_inserted + records_updated + records_failed
    success_rate = round((records_inserted + records_updated) / total_processed * 100, 2) if total_processed else 0.0
    db[COL_FACT_CRAWL_QUALITIES].insert_one({
        "crawl_job_id": None,
        "data_source_id": data_source_id,
        "market_id": market_id,
        "time_id": time_id,
        "records_fetched": records_fetched,
        "records_inserted": records_inserted,
        "records_updated": records_updated,
        "records_failed": records_failed,
        "success_rate": success_rate,
        "status": status,
        "created_at": utcnow(),
    })


# ═══════════════════════════════════════════════════════
# Providers
# ═══════════════════════════════════════════════════════
class MarketPriceProvider(Protocol):
    name: str

    def fetch(self, symbol: str, target_date: date, context: dict[str, Any]) -> dict[str, Any] | None:
        ...


@dataclass
class VietstockBrowserProvider:
    browser: VietstockBrowser
    name: str = "vietstock_browser"

    def fetch(self, symbol: str, target_date: date, context: dict[str, Any]) -> dict[str, Any] | None:
        slug = context.get("slug") or symbol.lower()
        profile_url = context.get("market_price_data_url") or f"https://finance.vietstock.vn/{symbol.lower()}-profile.htm"
        stats_url = context.get("trade_stats_url") or f"https://finance.vietstock.vn/{symbol.lower()}/thong-ke-giao-dich.htm"

        # Get load-more config from context
        max_load_more = context.get("max_load_more", 10)
        load_more_timeout = context.get("load_more_timeout", 5.0)
        debug_provider = context.get("debug_provider", False)

        enable_financial = os.getenv("ENABLE_FINANCIAL_DATA", "false").lower() == "true"
        market, financial = crawl_company(
            symbol=symbol,
            slug=slug,
            browser=self.browser,
            profile_url=profile_url,
            crawl_financial=enable_financial,
        )
        if market.get("error") or not market.get("is_valid_url"):
            raise RuntimeError(market.get("error") or "Không tải được trang profile")

        # Navigate to trading stats page and handle load-more
        self.browser.get_html(stats_url)
        click_count = 0
        found_target = False

        while True:
            html = self.browser.page.content()
            min_date, max_date = get_table_dates(html)
            row_count = get_table_row_count(html)

            hist_data = extract_historical_price_from_trading_stats(html, target_date)
            found_target = hist_data is not None

            min_date_str = min_date.strftime("%Y-%m-%d") if min_date else "None"
            max_date_str = max_date.strftime("%Y-%m-%d") if max_date else "None"

            # Log rõ các thông số yêu cầu
            if debug_provider:
                logger.info(
                    f"  [{symbol}] [Load-more Vietstock] "
                    f"Số dòng table hiện có: {row_count} | "
                    f"Min/Max date trong table: {min_date_str} -> {max_date_str} | "
                    f"Số lần đã click “Xem thêm”: {click_count} | "
                    f"Có tìm thấy target date ({target_date}) không: {'CÓ' if found_target else 'KHÔNG'}"
                )

            # Điều kiện dừng 1: tìm thấy target date
            if found_target:
                if debug_provider:
                    logger.info(f"  [{symbol}] ✅ Tìm thấy target date {target_date} ở lần click thứ {click_count}. Dừng ngay, không load thêm.")
                break

            # Điều kiện dừng 2: ngày nhỏ nhất trong table đã cũ hơn target date
            if min_date and min_date < target_date:
                if debug_provider:
                    logger.info(f"  [{symbol}] ⏹️ Dừng: ngày nhỏ nhất trong table ({min_date_str}) đã cũ hơn target date ({target_date})")
                break

            # Điều kiện dừng 3: đạt max_clicks (max_load_more)
            if click_count >= max_load_more:
                if debug_provider:
                    logger.info(f"  [{symbol}] ⏹️ Dừng: đạt max_clicks ({max_load_more})")
                break

            # Điều kiện dừng 4: hết nút “Xem thêm” (click_load_more trả về False)
            if not self.browser.click_load_more(timeout=load_more_timeout):
                if debug_provider:
                    logger.info(f"  [{symbol}] ⏹️ Dừng: hết nút “Xem thêm” hoặc không tải thêm được dữ liệu")
                break

            click_count += 1

        if not found_target:
            if debug_provider:
                logger.info(f"  [{symbol}] ❌ Không tìm thấy dữ liệu cho ngày {target_date} sau {click_count} lần click")
            return None

        result = {
            "open_price": hist_data.get("open"),
            "high_price": hist_data.get("high"),
            "low_price": hist_data.get("low"),
            "close_price": hist_data.get("close"),
            "reference": hist_data.get("reference"),
            "volume": hist_data.get("volume"),
            "market_cap": hist_data.get("market_cap"),
            "price_change": hist_data.get("price_change"),
            "price_change_percent": hist_data.get("price_change_percent"),
            "foreign_buy": hist_data.get("foreign_buy"),
            "foreign_sell": hist_data.get("foreign_sell"),
            "foreign_net": hist_data.get("foreign_net"),
            "bid_volume": hist_data.get("bid_volume"),
            "ask_volume": hist_data.get("ask_volume"),
            "eps": market.get("eps"),
            "pe": market.get("pe"),
            "forward_pe": market.get("forward_pe"),
            "bvps": market.get("bvps"),
            "pb": market.get("pb"),
            "beta": market.get("beta"),
            "roe": market.get("roe"),
            "roaa": market.get("roaa"),
            "ros": financial.get("ros") if financial else None,
        }
        return normalize_price_data(result)


@dataclass
class VietstockDataFeedProvider:
    name: str = "vietstock_datafeed"

    def fetch(self, symbol: str, target_date: date, context: dict[str, Any]) -> dict[str, Any] | None:
        api_url = os.getenv("VIETSTOCK_DATAFEED_API_URL")
        api_key = os.getenv("VIETSTOCK_DATAFEED_API_KEY")
        if not api_url or not api_key:
            return None

        # TODO: chỉnh endpoint/params theo hợp đồng API thật của Vietstock DataFeed.
        resp = requests.get(
            api_url.rstrip("/") + "/market-price",
            params={"symbol": symbol, "date": target_date.isoformat()},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json()
        return normalize_external_payload(payload)


@dataclass
class FiinTradeProvider:
    name: str = "fiintrade"

    def fetch(self, symbol: str, target_date: date, context: dict[str, Any]) -> dict[str, Any] | None:
        api_url = os.getenv("FIINTRADE_API_URL")
        api_key = os.getenv("FIINTRADE_API_KEY")
        if not api_url or not api_key:
            return None

        # TODO: chỉnh endpoint/params theo hợp đồng API thật của FiinTrade/FiinQuant.
        resp = requests.get(
            api_url.rstrip("/") + "/prices",
            params={"ticker": symbol, "date": target_date.isoformat()},
            headers={"X-API-Key": api_key},
            timeout=20,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json()
        return normalize_external_payload(payload)


@dataclass
class EODHDProvider:
    name: str = "eodhd"

    def fetch(self, symbol: str, target_date: date, context: dict[str, Any]) -> dict[str, Any] | None:
        api_key = os.getenv("EODHD_API_KEY")
        if not api_key:
            return None

        # EODHD thường chỉ đủ OHLCV, dùng fallback cho field bắt buộc.
        ticker = f"{symbol}.VN"
        url = f"https://eodhd.com/api/eod/{ticker}"
        resp = requests.get(
            url,
            params={"api_token": api_key, "fmt": "json", "from": target_date.isoformat(), "to": target_date.isoformat()},
            timeout=20,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list) and payload:
            row = payload[0]
        elif isinstance(payload, dict):
            row = payload
        else:
            return None
        return normalize_external_payload(row)


def normalize_external_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Map payload API ngoài về field factMarketPrices."""
    data = {
        "open_price": payload.get("open_price", payload.get("open")),
        "high_price": payload.get("high_price", payload.get("high")),
        "low_price": payload.get("low_price", payload.get("low")),
        "close_price": payload.get("close_price", payload.get("close", payload.get("adjusted_close"))),
        "volume": payload.get("volume"),
        "bid_volume": payload.get("bid_volume"),
        "ask_volume": payload.get("ask_volume"),
        "foreign_buy": payload.get("foreign_buy"),
        "foreign_sell": payload.get("foreign_sell"),
        "foreign_net": payload.get("foreign_net"),
        "market_cap": payload.get("market_cap"),
        "eps": payload.get("eps"),
        "pe": payload.get("pe"),
        "forward_pe": payload.get("forward_pe"),
        "bvps": payload.get("bvps"),
        "pb": payload.get("pb"),
        "beta": payload.get("beta"),
        "ros": payload.get("ros"),
        "roe": payload.get("roe"),
        "roaa": payload.get("roaa"),
        "price_change": payload.get("price_change", payload.get("change")),
        "price_change_percent": payload.get("price_change_percent", payload.get("change_percent")),
        "reference": payload.get("reference", payload.get("ref_price")),
    }
    return normalize_price_data(data)


def build_providers(provider_names: list[str], browser: VietstockBrowser) -> list[MarketPriceProvider]:
    registry: dict[str, MarketPriceProvider] = {
        "vietstock": VietstockBrowserProvider(browser),
        "vietstock_browser": VietstockBrowserProvider(browser),
        "vietstock_datafeed": VietstockDataFeedProvider(),
        "fiintrade": FiinTradeProvider(),
        "fiinquant": FiinTradeProvider(name="fiinquant"),
        "eodhd": EODHDProvider(),
    }
    providers: list[MarketPriceProvider] = []
    for name in provider_names:
        key = name.strip().lower()
        if not key:
            continue
        provider = registry.get(key)
        if provider:
            providers.append(provider)
        else:
            logger.warning(f"⚠️ Provider không hỗ trợ: {name}")
    if not providers:
        providers = [registry["vietstock"]]
    return providers


def fetch_market_price(symbol: str, target_date: date, context: dict[str, Any], providers: list[MarketPriceProvider]) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    final_data: dict[str, Any] = {}
    source_used: list[str] = []
    provider_errors: list[str] = []

    for provider in providers:
        try:
            data = provider.fetch(symbol, target_date, context)
            if not data:
                continue
            before = dict(final_data)
            final_data = merge_missing_fields(final_data, data)
            if final_data != before:
                source_used.append(provider.name)

            # Nếu đã đủ toàn bộ field quality thì dừng sớm.
            if not get_missing_fields(final_data, ALL_QUALITY_FIELDS):
                break
        except Exception as exc:
            provider_errors.append(f"{provider.name}: {exc}")
            logger.warning(f"  [{symbol}] Provider {provider.name} lỗi: {exc}")

    if not final_data:
        return None, source_used, provider_errors
    return normalize_price_data(final_data), source_used, provider_errors


# ═══════════════════════════════════════════════════════
# Vietstock HTML parser
# ═══════════════════════════════════════════════════════
def parse_table_row(cells: list[str]) -> dict[str, Any] | None:
    """Parse a single table row and extract price data."""
    from vietstock_crawler.utils.number_utils import normalize_number

    if len(cells) < 8:
        return None

    def safe_num(idx: int):
        if idx >= len(cells):
            return None
        return normalize_number(cells[idx])

    volume = safe_num(11)
    if volume is not None:
        volume = int(volume * 1_000_000)  # Vietstock hiển thị triệu CP

    market_cap = safe_num(17)
    if market_cap is not None:
        market_cap = market_cap * 1_000_000_000  # tỷ đồng

    foreign_buy = safe_num(18)
    foreign_sell = safe_num(19)
    foreign_net = None
    if foreign_buy is not None and foreign_sell is not None:
        foreign_net = foreign_buy - foreign_sell

    return {
        "reference": safe_num(3),
        "open": safe_num(4),
        "close": safe_num(5),
        "high": safe_num(6),
        "low": safe_num(7),
        "price_change": safe_num(9),
        "price_change_percent": safe_num(10),
        "volume": volume,
        "market_cap": market_cap,
        "bid_volume": None,
        "ask_volume": None,
        "foreign_buy": foreign_buy,
        "foreign_sell": foreign_sell,
        "foreign_net": foreign_net,
    }


def extract_date_from_cell(cell_text: str) -> date | None:
    """Extract date from a cell text, trying multiple formats."""
    for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(cell_text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def get_table_dates(html: str) -> tuple[date | None, date | None]:
    """Extract min and max dates from historical price table in HTML."""
    soup = BeautifulSoup(html, "html.parser")
    dates_found = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            for cell in cells[:3]:
                parsed = extract_date_from_cell(cell)
                if parsed:
                    dates_found.append(parsed)
                    break

    if dates_found:
        return min(dates_found), max(dates_found)
    return None, None


def get_table_row_count(html: str) -> int:
    """Count data rows in historical price table."""
    soup = BeautifulSoup(html, "html.parser")
    row_count = 0
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 8:
                row_count += 1
    return row_count


def extract_historical_price_from_trading_stats(html: str, target_date: date) -> dict[str, Any] | None:
    """Extract historical price data for target date from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    date_options = {
        target_date.strftime("%d/%m/%Y"),
        f"{target_date.day}/{target_date.month}/{target_date.year}",
        target_date.strftime("%d/%m/%y"),
    }

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 8:
                continue

            date_cell_candidates = cells[:3]
            if not any(c in date_options for c in date_cell_candidates):
                continue

            return parse_table_row(cells)
    return None


# ═══════════════════════════════════════════════════════
# Map + upsert
# ═══════════════════════════════════════════════════════
def map_to_fact_market_price(raw_data: dict[str, Any], stock_id: ObjectId, market_id: ObjectId, industry_id: ObjectId | None, data_source_id: ObjectId, time_id: int, source_used: list[str]) -> dict[str, Any]:
    now = utcnow()
    missing_required = get_missing_fields(raw_data, REQUIRED_FIELDS)
    missing_all = get_missing_fields(raw_data, ALL_QUALITY_FIELDS)

    return {
        "stock_id": stock_id,
        "market_id": market_id,
        "industry_id": industry_id,
        "data_source_id": data_source_id,
        "time_id": time_id,
        "open_price": raw_data.get("open_price"),
        "high_price": raw_data.get("high_price"),
        "low_price": raw_data.get("low_price"),
        "close_price": raw_data.get("close_price"),
        "volume": raw_data.get("volume"),
        "bid_volume": raw_data.get("bid_volume"),
        "ask_volume": raw_data.get("ask_volume"),
        "foreign_buy": raw_data.get("foreign_buy"),
        "foreign_sell": raw_data.get("foreign_sell"),
        "foreign_net": raw_data.get("foreign_net"),
        "market_cap": raw_data.get("market_cap"),
        "eps": raw_data.get("eps"),
        "pe": raw_data.get("pe"),
        "forward_pe": raw_data.get("forward_pe"),
        "bvps": raw_data.get("bvps"),
        "pb": raw_data.get("pb"),
        "beta": raw_data.get("beta"),
        "ros": raw_data.get("ros"),
        "roe": raw_data.get("roe"),
        "roaa": raw_data.get("roaa"),
        "price_change": raw_data.get("price_change"),
        "price_change_percent": raw_data.get("price_change_percent"),
        "data_completeness": calculate_data_completeness(raw_data),
        "missing_fields": missing_all,
        "missing_required_fields": missing_required,
        "source_used": source_used,
        "crawled_at": now,
        "updated_at": now,
    }


def upsert_fact_market_price(db, doc: dict[str, Any]) -> tuple[int, int]:
    col = db[COL_FACT_MARKET_PRICES]
    filter_query = {
        "stock_id": doc["stock_id"],
        "time_id": doc["time_id"],
        "data_source_id": doc["data_source_id"],
    }
    created_at = doc.pop("created_at", utcnow())
    result = col.update_one(filter_query, {"$set": doc, "$setOnInsert": {"created_at": created_at}}, upsert=True)
    if result.upserted_id:
        return 1, 0
    if result.modified_count > 0:
        return 0, 1
    return 0, 0


# ═══════════════════════════════════════════════════════
# Standalone Symbol Crawl Logic & Timeout Wrapper
# ═══════════════════════════════════════════════════════
def crawl_single_symbol(
    db,
    stock: dict[str, Any],
    target_date: date,
    provider_names: list[str],
    data_source_id: ObjectId,
    time_id: int,
    hose_market_id: ObjectId | None,
    is_dry_run: bool,
    crawl_log_id: ObjectId,
    timeout: float | None = None
) -> dict[str, Any]:
    """
    Crawls a single symbol. Opens its own browser session to be thread-safe,
    and performs MongoDB saving.
    """
    symbol = stock.get("symbol", "???").upper()
    stock_id = stock["_id"]
    market_id = stock.get("market_id") or hose_market_id
    industry_id = stock.get("industry_id")
    slug = stock.get("slug") or symbol.lower()

    with VietstockBrowser(timeout=timeout) as browser:
        providers = build_providers(provider_names, browser)
        stock_ds = get_or_create_stock_data_source(db, stock, dry_run=is_dry_run)
        current_ds_id = stock_ds.get("_id") or data_source_id
        context = {
            "slug": slug,
            "market_price_data_url": stock_ds.get("market_price_data_url"),
            "trade_stats_url": stock_ds.get("trade_stats_url"),
            "financial_data_url": stock_ds.get("financial_data_url"),
        }

        raw_data, source_used, provider_errors = fetch_market_price(symbol, target_date, context, providers)

        if raw_data is None:
            if provider_errors:
                raise RuntimeError(f"Provider errors: {' | '.join(provider_errors)}")
            msg = f"Không có dữ liệu cho ngày {target_date}."
            logger.warning(f"  [{symbol}] {msg}")
            if not is_dry_run:
                write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "SKIPPED", msg)
            return {
                "status": "SKIPPED",
                "message": msg
            }

        missing_required = get_missing_fields(raw_data, REQUIRED_FIELDS)
        missing_all = get_missing_fields(raw_data, ALL_QUALITY_FIELDS)
        completeness = calculate_data_completeness(raw_data)

        if missing_required:
            if provider_errors:
                raise RuntimeError(f"Thiếu field bắt buộc {missing_required} do provider lỗi: {' | '.join(provider_errors)}")
            msg = f"Thiếu field bắt buộc: {missing_required}; completeness={completeness}%; source={source_used}"
            logger.warning(f"  [{symbol}] ⚠️ SKIPPED - {msg}")
            if not is_dry_run:
                write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "SKIPPED", msg)
            return {
                "status": "SKIPPED",
                "message": msg
            }

        # Apply fallback for market_id if it's missing/null
        if not market_id and hose_market_id:
            market_id = hose_market_id

        fact_doc = map_to_fact_market_price(
            raw_data=raw_data,
            stock_id=stock_id,
            market_id=market_id,
            industry_id=industry_id,
            data_source_id=current_ds_id,
            time_id=time_id,
            source_used=source_used,
        )

        if is_dry_run:
            logger.info(
                f"  [{symbol}] ✅ [DRY RUN] completeness={completeness}%, "
                f"missing={missing_all}, source={source_used}, data={raw_data}"
            )
            return {
                "status": "SUCCESS",
                "action": "INSERT",
                "inserted": 1,
                "updated": 0,
                "raw_data": raw_data,
                "source_used": source_used,
                "completeness": completeness,
                "missing_all": missing_all
            }

        inserted, updated = upsert_fact_market_price(db, fact_doc)
        action = "INSERT" if inserted else ("UPDATE" if updated else "UNCHANGED")
        logger.info(f"  [{symbol}] ✅ {action} | completeness={completeness}% | missing={missing_all} | source={source_used}")

        success_msg = f"{action}: close={raw_data.get('close_price')}, volume={raw_data.get('volume')}, completeness={completeness}%, missing={missing_all}, source={source_used}"
        write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "SUCCESS", success_msg)

        return {
            "status": "SUCCESS",
            "action": action,
            "inserted": inserted,
            "updated": updated,
            "raw_data": raw_data,
            "source_used": source_used,
            "completeness": completeness,
            "missing_all": missing_all
        }


def crawl_symbol_with_timeout(
    db,
    stock: dict[str, Any],
    target_date: date,
    provider_names: list[str],
    data_source_id: ObjectId,
    time_id: int,
    hose_market_id: ObjectId | None,
    is_dry_run: bool,
    crawl_log_id: ObjectId,
    timeout: float = 25.0
) -> dict[str, Any]:
    """
    Runs the crawl function inside a ThreadPoolExecutor with a hard timeout.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        crawl_single_symbol,
        db=db,
        stock=stock,
        target_date=target_date,
        provider_names=provider_names,
        data_source_id=data_source_id,
        time_id=time_id,
        hose_market_id=hose_market_id,
        is_dry_run=is_dry_run,
        crawl_log_id=crawl_log_id,
        timeout=timeout
    )
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(f"Timeout > {timeout}s")
    finally:
        executor.shutdown(wait=False)


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Crawl thủ công dữ liệu chứng khoán HOSE theo ngày bất kỳ.")
    parser.add_argument("--date", required=True, help="Ngày crawl dạng YYYY-MM-DD. Ví dụ: 2026-05-22")
    parser.add_argument("--source", default=DATA_SOURCE_NAME, help=f"Tên data source tổng (mặc định: {DATA_SOURCE_NAME})")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay giữa các mã cổ phiếu")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử, không lưu DB")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số mã crawl để test")
    parser.add_argument(
        "--providers",
        default="vietstock,fiintrade,vietstock_datafeed,eodhd",
        help="Danh sách provider theo thứ tự ưu tiên, phân tách bằng dấu phẩy",
    )
    parser.add_argument("--max-load-more", type=int, default=10, help="Số lần tối đa click 'Xem thêm' (mặc định: 10)")
    parser.add_argument("--load-more-timeout", type=float, default=5.0, help="Timeout giây chờ click 'Xem thêm' (mặc định: 5)")
    parser.add_argument("--debug-provider", action="store_true", help="Bật log debug cho provider")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    is_dry_run = args.dry_run
    if is_dry_run:
        logger.info("🔍 DRY RUN MODE – không lưu dữ liệu vào database")

    client, db = connect_mongodb()

    try:
        data_source_id = get_or_create_data_source(db, args.source) if not is_dry_run else ObjectId()
        time_id = get_or_create_dim_time(db, target_date) if not is_dry_run else date_to_time_id(target_date)

        stocks = get_active_hose_stocks(db)
        if not stocks:
            logger.error("❌ Không tìm thấy mã cổ phiếu nào trong database. Hãy kiểm tra dimMarkets/dimstocks/market_id/status.")
            sys.exit(1)

        if args.limit > 0:
            stocks = stocks[: args.limit]
            logger.info(f"🔧 Giới hạn test: chỉ crawl {len(stocks)} mã đầu tiên")

        crawl_log_id = create_crawl_log(db, time_id) if not is_dry_run else ObjectId()
        hose_market = db[COL_DIM_MARKETS].find_one({"code": {"$in": ["HOSE", "hose"]}})
        hose_market_id = hose_market["_id"] if hose_market else None

        total = len(stocks)
        
        # Tracking states
        success_first = []
        success_retry = []
        failed_retry = []
        skipped_list = []
        
        retry_symbols = []
        
        cnt_inserted = cnt_updated = 0

        logger.info("\n" + "═" * 70)
        logger.info(f"🚀 Bắt đầu crawl {total} mã HOSE ngày {target_date}")
        logger.info(f"🔁 Providers: {args.providers}")
        logger.info("═" * 70 + "\n")

        settings = get_settings()
        provider_names = [p.strip() for p in args.providers.split(",") if p.strip()]

        # Main Queue Execution
        for idx, stock in enumerate(stocks, start=1):
            symbol = stock.get("symbol", "???").upper()
            logger.info(f"[{idx}/{total}] ▶ {symbol} ...")

            start_time = time.time()
            try:
                result = crawl_symbol_with_timeout(
                    db=db,
                    stock=stock,
                    target_date=target_date,
                    provider_names=provider_names,
                    data_source_id=data_source_id,
                    time_id=time_id,
                    hose_market_id=hose_market_id,
                    is_dry_run=is_dry_run,
                    crawl_log_id=crawl_log_id,
                    timeout=settings.symbol_crawl_timeout
                )
                if result["status"] == "SUCCESS":
                    success_first.append(symbol)
                    cnt_inserted += result.get("inserted", 0)
                    cnt_updated += result.get("updated", 0)
                elif result["status"] == "SKIPPED":
                    skipped_list.append(symbol)

            except Exception as exc:
                execution_time = time.time() - start_time
                err_msg = str(exc)
                if isinstance(exc, TimeoutError) or "Timeout >" in err_msg:
                    logger.warning(f"  [{symbol}] TIMEOUT after {execution_time:.1f}s")
                    reason = "timeout"
                else:
                    logger.warning(f"  [{symbol}] ERROR after {execution_time:.1f}s: {err_msg}")
                    reason = err_msg

                retry_symbols.append({
                    "symbol": symbol,
                    "reason": reason,
                    "attempt": 2,
                    "stock": stock
                })

            if args.delay > 0 and idx < total:
                time.sleep(args.delay)

        # Retry Phase
        if retry_symbols:
            logger.info("\n" + "═" * 70)
            logger.info("=== RETRY PHASE START ===")
            logger.info("═" * 70 + "\n")

            while retry_symbols:
                item = retry_symbols.pop(0)
                symbol = item["symbol"]
                attempt = item["attempt"]
                stock = item["stock"]
                stock_id = stock["_id"]
                reason = item["reason"]

                logger.info(f"[{symbol}] Retry {attempt}/3")

                start_time = time.time()
                try:
                    stock_ds = get_or_create_stock_data_source(db, stock, dry_run=is_dry_run)
                    current_ds_id = stock_ds.get("_id") or data_source_id
                    context = {
                        "slug": slug,
                        "market_price_data_url": stock_ds.get("market_price_data_url"),
                        "trade_stats_url": stock_ds.get("trade_stats_url"),
                        "financial_data_url": stock_ds.get("financial_data_url"),
                        "max_load_more": args.max_load_more,
                        "load_more_timeout": args.load_more_timeout,
                        "debug_provider": args.debug_provider,
                    }

                    raw_data, source_used, provider_errors = fetch_market_price(symbol, target_date, context, providers)

                    if raw_data is None:
                        cnt_skipped += 1
                        msg = f"Không có dữ liệu cho ngày {target_date}. Provider errors: {' | '.join(provider_errors)}"
                        logger.warning(f"  [{symbol}] {msg}")
                        if not is_dry_run:
                            write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "SKIPPED", msg)
                        continue

                    missing_required = get_missing_fields(raw_data, REQUIRED_FIELDS)
                    missing_all = get_missing_fields(raw_data, ALL_QUALITY_FIELDS)
                    completeness = calculate_data_completeness(raw_data)

                    if missing_required:
                        cnt_skipped += 1
                        msg = f"Thiếu field bắt buộc: {missing_required}; completeness={completeness}%; source={source_used}"
                        logger.warning(f"  [{symbol}] ⚠️ SKIPPED - {msg}")
                        if not is_dry_run:
                            write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "SKIPPED", msg)
                        continue

                    cnt_fetched += 1

                    fact_doc = map_to_fact_market_price(
                        raw_data=raw_data,
                        stock_id=stock_id,
                        market_id=market_id,
                        industry_id=industry_id,
                        data_source_id=current_ds_id,
                        time_id=time_id,
                        hose_market_id=hose_market_id,
                        is_dry_run=is_dry_run,
                        crawl_log_id=crawl_log_id,
                        timeout=settings.symbol_crawl_timeout
                    )
                    if result["status"] == "SUCCESS":
                        success_retry.append(symbol)
                        cnt_inserted += result.get("inserted", 0)
                        cnt_updated += result.get("updated", 0)
                        logger.info(f"  [{symbol}] Retried SUCCESS on attempt {attempt}")
                    elif result["status"] == "SKIPPED":
                        skipped_list.append(symbol)
                        logger.info(f"  [{symbol}] Retried SKIPPED on attempt {attempt}")

                except Exception as exc:
                    execution_time = time.time() - start_time
                    err_msg = str(exc)
                    if isinstance(exc, TimeoutError) or "Timeout >" in err_msg:
                        logger.warning(f"  [{symbol}] TIMEOUT after {execution_time:.1f}s")
                        new_reason = "timeout"
                    else:
                        logger.warning(f"  [{symbol}] ERROR after {execution_time:.1f}s: {err_msg}")
                        new_reason = err_msg

                    if attempt < 3:
                        logger.warning(f"  [{symbol}] Attempt {attempt} failed ({new_reason}), will retry again")
                        retry_symbols.append({
                            "symbol": symbol,
                            "reason": new_reason,
                            "attempt": attempt + 1,
                            "stock": stock
                        })
                    else:
                        failed_retry.append(symbol)
                        logger.error(f"  [{symbol}] FAILED AFTER 3 RETRIES")
                        if not is_dry_run:
                            write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "FAILED", f"FAILED AFTER 3 RETRIES: {new_reason}")

                if args.delay > 0 and len(retry_symbols) > 0:
                    time.sleep(args.delay)

        cnt_fetched = len(success_first) + len(success_retry)
        cnt_failed = len(failed_retry)
        cnt_skipped = len(skipped_list)

        if cnt_failed == 0 and cnt_fetched > 0:
            final_status = "SUCCESS"
        elif cnt_fetched == 0 and cnt_failed == 0:
            final_status = "FAILED"
        elif cnt_failed > 0 and (cnt_inserted + cnt_updated) == 0:
            final_status = "FAILED"
        elif cnt_failed > 0:
            final_status = "PARTIAL_SUCCESS"
        else:
            final_status = "SUCCESS"

        logger.info("\n=================================================")
        logger.info("CRAWL SUMMARY")
        logger.info("=============\n")
        logger.info(f"Total symbols: {total}")
        logger.info(f"Success: {len(success_first)}")
        logger.info(f"Retried Success: {len(success_retry)}")
        logger.info(f"Failed After Retry: {len(failed_retry)}")
        logger.info("=====================\n")
        if failed_retry:
            logger.info("Failed symbols:\n")
            for fs in failed_retry:
                logger.info(f"* {fs}")
        else:
            logger.info("No failed symbols.")
        logger.info("\n" + "═" * 70)

        if not is_dry_run:
            finalize_crawl_log(db, crawl_log_id, cnt_fetched, cnt_inserted, cnt_updated, cnt_failed, cnt_skipped, final_status)
            write_fact_crawl_quality(db, data_source_id, hose_market_id, time_id, cnt_fetched, cnt_inserted, cnt_updated, cnt_failed, final_status)

    finally:
        client.close()
        logger.info("🔒 Đã đóng kết nối MongoDB")


if __name__ == "__main__":
    main()
