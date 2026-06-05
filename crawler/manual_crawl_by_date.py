"""
manual_crawl_by_date_v2.py
--------------------------
Crawl thủ công dữ liệu chứng khoán theo ngày bất kỳ.
Phiên bản v2: Multi-source fallback để đảm bảo tất cả trường đầy đủ,
kể cả khi crawl ngày trong quá khứ.

Chiến lược nguồn dữ liệu:
  Nguồn 1 – Vietstock (Playwright)   : OHLCV, market_cap, price_change
  Nguồn 2 – TCBS API (miễn phí)     : EPS, PE, PB, ROE, ROAA, ROS, beta,
                                       foreign_buy, foreign_sell, foreign_net
  Nguồn 3 – SSI iBoard API (miễn phí): bid_volume, ask_volume, foreign (backup)

Cách dùng:
    python manual_crawl_by_date_v2.py --date 2026-05-22
    python manual_crawl_by_date_v2.py --date 2026-05-22 --delay 0.3 --dry-run
    python manual_crawl_by_date_v2.py --date 2026-05-22 --limit 5

Yêu cầu file .env cùng thư mục:
    MONGODB_URI=...
    MONGODB_DB_NAME=...          (tuỳ chọn)
    ENABLE_FINANCIAL_DATA=false  (tuỳ chọn)
    HTTP_TIMEOUT=15              (tuỳ chọn, giây)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

# ── Path setup ──────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vietstock_crawler.core.browser import VietstockBrowser
from vietstock_crawler.services.vietstock_service import crawl_company
from vietstock_crawler.utils.number_utils import normalize_number

# ── Fix Unicode cho Windows terminal ────────────────────
import io
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Logging ─────────────────────────────────────────────
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────
DATA_SOURCE_NAME        = "vietstock"
DATA_SOURCE_PROVIDER    = "browser_crawler"
DATA_SOURCE_DESCRIPTION = "Playwright crawler + TCBS/SSI API fallback"

COL_DIM_STOCKS         = "dimstocks"
COL_DIM_TIMES          = "dimTimes"
COL_DIM_DATA_SOURCES   = "dimDataSources"
COL_DIM_MARKETS        = "dimMarkets"
COL_FACT_MARKET_PRICES = "factMarketPrices"
COL_CRAWL_LOGS         = "crawlLogs"
COL_CRAWL_LOG_DETAILS  = "crawlLogDetails"
COL_FACT_CRAWL_QUALITY = "factCrawlQualities"

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))

# Shared requests session (connection reuse, common headers)
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
})


# ═══════════════════════════════════════════════════════
# 1. MONGODB
# ═══════════════════════════════════════════════════════
def connect_mongodb():
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    if not uri:
        logger.error("Không tìm thấy MONGODB_URI trong file .env")
        sys.exit(1)
    db_name = os.getenv("MONGODB_DB_NAME")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
        client.admin.command("ping")
        db = client[db_name] if db_name else client.get_default_database()
        logger.info(f"✅ Kết nối MongoDB thành công. Database: {db.name}")
        return client, db
    except Exception as e:
        logger.error(f"❌ Không thể kết nối MongoDB: {e}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════
# 2. PARSE NGÀY
# ═══════════════════════════════════════════════════════
def parse_date(date_str: str) -> date:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        logger.info(f"📅 Ngày crawl: {d.strftime('%d/%m/%Y')}")
        return d
    except ValueError:
        logger.error(f"❌ Định dạng ngày không hợp lệ: '{date_str}'. Dùng YYYY-MM-DD.")
        sys.exit(1)


def date_to_time_id(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


# ═══════════════════════════════════════════════════════
# 3. DIM HELPERS (time, data_source, crawl_log …)
# ═══════════════════════════════════════════════════════
def get_active_hose_stocks(db) -> list[dict]:
    market = db[COL_DIM_MARKETS].find_one({"code": "HOSE"})
    if not market:
        logger.error("❌ Không tìm thấy HOSE market")
        return []
    stocks = list(db[COL_DIM_STOCKS].find(
        {"market_id": market["_id"], "status": {"$in": ["ACTIVE", "active"]}},
        {"_id": 1, "symbol": 1, "market_id": 1, "industry_id": 1, "slug": 1},
    ))
    logger.info(f"📊 Tìm thấy {len(stocks)} mã HOSE đang hoạt động")
    return stocks


def get_or_create_dim_time(db, d: date) -> int:
    col = db[COL_DIM_TIMES]
    time_id = date_to_time_id(d)
    if col.find_one({"time_id": time_id}):
        return time_id
    import calendar
    doc = {
        "time_id": time_id,
        "full_date": datetime(d.year, d.month, d.day),
        "day": d.day, "month": d.month,
        "quarter": (d.month - 1) // 3 + 1,
        "year": d.year,
        "week_of_year": d.isocalendar()[1],
        "weekday": d.weekday(),
        "is_trading_day": d.weekday() < 5,
        "created_at": datetime.utcnow(),
    }
    try:
        col.insert_one(doc)
        logger.info(f"📆 Đã tạo dim_time: {time_id}")
    except Exception:
        pass
    return time_id


def get_or_create_data_source(db, name: str = DATA_SOURCE_NAME) -> ObjectId:
    col = db[COL_DIM_DATA_SOURCES]
    existing = col.find_one({"name": name})
    if existing:
        return existing["_id"]
    result = col.insert_one({
        "name": name, "provider_type": DATA_SOURCE_PROVIDER,
        "base_url": "", "description": DATA_SOURCE_DESCRIPTION,
        "status": "active",
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
    })
    return result.inserted_id


def create_crawl_log(db, time_id: int) -> ObjectId:
    result = db[COL_CRAWL_LOGS].insert_one({
        "crawl_job_id": None, "started_at": datetime.utcnow(),
        "ended_at": None, "status": "PENDING",
        "records_fetched": 0, "records_inserted": 0,
        "records_updated": 0, "records_failed": 0,
        "error_message": f"Manual crawl time_id={time_id}",
        "created_at": datetime.utcnow(),
    })
    return result.inserted_id


def write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, status, message="", data_type="market_price"):
    db[COL_CRAWL_LOG_DETAILS].insert_one({
        "crawl_log_id": crawl_log_id, "stock_id": stock_id,
        "symbol": symbol, "data_type": data_type,
        "status": status, "message": message,
        "created_at": datetime.utcnow(),
    })


def finalize_crawl_log(db, crawl_log_id, fetched, inserted, updated, failed, skipped, status):
    db[COL_CRAWL_LOGS].update_one({"_id": crawl_log_id}, {"$set": {
        "ended_at": datetime.utcnow(), "status": status,
        "records_fetched": fetched, "records_inserted": inserted,
        "records_updated": updated, "records_failed": failed,
        "error_message": f"Skipped: {skipped}",
    }})


def write_fact_crawl_quality(db, data_source_id, market_id, time_id, fetched, inserted, updated, failed, status):
    total = inserted + updated + failed
    rate  = round((inserted + updated) / total * 100, 2) if total > 0 else 0.0
    db[COL_FACT_CRAWL_QUALITY].insert_one({
        "crawl_job_id": None, "data_source_id": data_source_id,
        "market_id": market_id, "time_id": time_id,
        "records_fetched": fetched, "records_inserted": inserted,
        "records_updated": updated, "records_failed": failed,
        "success_rate": rate, "status": status,
        "created_at": datetime.utcnow(),
    })


# ═══════════════════════════════════════════════════════
# 4. NGUỒN 1 – VIETSTOCK (Playwright)
#    Lấy: OHLCV, market_cap, price_change, price_change_pct
#    (giữ nguyên logic cũ, chỉ trả về dict chuẩn hoá)
# ═══════════════════════════════════════════════════════
def _parse_trading_stats_html(html: str, target_date: date) -> Optional[dict]:
    """
    Parse trang 'thong-ke-giao-dich.htm' của Vietstock.
    Trả về dict OHLCV hoặc None nếu không tìm thấy ngày.
    """
    soup = BeautifulSoup(html, "html.parser")
    target_strs = {
        target_date.strftime("%d/%m/%Y"),
        f"{target_date.day}/{target_date.month}/{target_date.year}",
        target_date.strftime("%d/%m/%y"),
    }
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 12:
                continue
            if cells[1].strip() not in target_strs:
                continue

            vol_raw = normalize_number(cells[11])
            mc_raw  = normalize_number(cells[17]) if len(cells) > 17 else None

            return {
                "open_price":           normalize_number(cells[4]),
                "high_price":           normalize_number(cells[6]),
                "low_price":            normalize_number(cells[7]),
                "close_price":          normalize_number(cells[5]),
                "reference_price":      normalize_number(cells[3]),
                "volume":               int(vol_raw * 1_000_000) if vol_raw is not None else None,
                "market_cap":           mc_raw * 1_000_000_000   if mc_raw  is not None else None,
                "price_change":         normalize_number(cells[9]),
                "price_change_percent": normalize_number(cells[10]),
            }
    return None


def fetch_vietstock(
    symbol: str,
    target_date: date,
    browser: VietstockBrowser,
    slug: str,
    profile_url: str,
    stats_url: str,
) -> dict:
    """
    Lấy dữ liệu từ Vietstock qua Playwright.
    Trả về dict (các key có thể None nếu không có dữ liệu).
    """
    result: dict = {}

    # 4a. Profile page → chỉ số tài chính hiện tại
    enable_financial = os.getenv("ENABLE_FINANCIAL_DATA", "false").lower() == "true"
    market, financial = crawl_company(
        symbol=symbol, slug=slug, browser=browser,
        profile_url=profile_url, crawl_financial=enable_financial,
    )
    if not market.get("error") and market.get("is_valid_url"):
        result.update({
            "eps":        market.get("eps"),
            "pe":         market.get("pe"),
            "forward_pe": market.get("forward_pe"),
            "bvps":       market.get("bvps"),
            "pb":         market.get("pb"),
            "beta":       market.get("beta"),
            "roe":        market.get("roe"),
            "roaa":       market.get("roaa"),
            "ros":        financial.get("ros"),
        })
        # bid/ask & foreign chỉ lấy nếu crawl hôm nay
        if target_date == date.today():
            result.update({
                "bid_volume":  market.get("bid_volume"),
                "ask_volume":  market.get("ask_volume"),
                "foreign_buy": market.get("foreign_buy"),
                "foreign_sell":market.get("foreign_sell"),
                "foreign_net": market.get("foreign_net"),
            })

    # 4b. Trang thống kê giao dịch → OHLCV lịch sử
    if not stats_url:
        stats_url = f"https://finance.vietstock.vn/{symbol.lower()}/thong-ke-giao-dich.htm"
    html = browser.get_html(stats_url)
    ohlcv = _parse_trading_stats_html(html, target_date)
    if ohlcv:
        result.update(ohlcv)

    return result


# ═══════════════════════════════════════════════════════
# 5. NGUỒN 2 – TCBS API (miễn phí, không cần đăng nhập)
#    Endpoint chính thức của TCBS cho dữ liệu lịch sử
#
#    Lấy: close/open/high/low/volume (backup OHLCV),
#         eps, pe, pb, roe, roaa, foreign_buy/sell/net
# ═══════════════════════════════════════════════════════

# Base URL TCBS
_TCBS_BASE = "https://apipubaws.tcbs.com.vn"


def _tcbs_get(path: str, params: dict | None = None) -> dict | list | None:
    """Wrapper GET cho TCBS API, trả về JSON hoặc None nếu lỗi."""
    url = f"{_TCBS_BASE}{path}"
    try:
        r = _session.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"TCBS API lỗi [{path}]: {e}")
        return None


def fetch_tcbs_historical_price(symbol: str, target_date: date) -> dict:
    """
    Lấy OHLCV lịch sử từ TCBS stock-insight API.
    Endpoint: /stock-insight/v2/stock/bars-long-term
    Trả về dict các trường giá hoặc {} nếu không tìm thấy.
    """
    # Lấy 5 ngày xung quanh để tìm chính xác ngày target
    from_ts = int(datetime(target_date.year, target_date.month, target_date.day).timestamp()) - 86400 * 3
    to_ts   = from_ts + 86400 * 6

    data = _tcbs_get("/stock-insight/v2/stock/bars-long-term", params={
        "ticker": symbol.upper(),
        "type":   "stock",
        "resolution": "D",
        "from": from_ts,
        "to":   to_ts,
    })

    if not data or not isinstance(data, dict):
        return {}

    bars = data.get("data", [])
    target_str = target_date.strftime("%Y-%m-%d")

    for bar in bars:
        # TCBS trả về timestamp (Unix) hoặc chuỗi ngày tuỳ endpoint version
        bar_date = bar.get("tradingDate") or bar.get("date") or ""
        if isinstance(bar_date, int):
            bar_date = datetime.utcfromtimestamp(bar_date).strftime("%Y-%m-%d")
        if bar_date[:10] != target_str:
            continue

        return {
            "open_price":  _safe_float(bar.get("open")),
            "high_price":  _safe_float(bar.get("high")),
            "low_price":   _safe_float(bar.get("low")),
            "close_price": _safe_float(bar.get("close")),
            "volume":      _safe_int(bar.get("volume")),
        }

    return {}


def fetch_tcbs_financials(symbol: str, target_date: date) -> dict:
    """
    Lấy chỉ số tài chính lịch sử từ TCBS.
    Endpoint: /stock-insight/v1/finance/financialratio

    Trả về dict: eps, pe, pb, roe, roaa, ros, beta,
                 foreign_buy, foreign_sell, foreign_net
    """
    result: dict = {}

    # ── Chỉ số định giá theo quý ──────────────────────────────────
    # TCBS trả về list theo quý, tìm quý gần nhất với target_date
    ratio_data = _tcbs_get("/stock-insight/v1/finance/financialratio", params={
        "ticker": symbol.upper(),
        "type":   "quarterly",
        "size":   8,
    })
    if ratio_data and isinstance(ratio_data, dict):
        items = ratio_data.get("data", [])
        best  = _find_closest_quarterly(items, target_date)
        if best:
            result.update({
                "eps":  _safe_float(best.get("eps")),
                "pe":   _safe_float(best.get("pe")),
                "pb":   _safe_float(best.get("pb")),
                "roe":  _safe_float(best.get("roe")),
                "roaa": _safe_float(best.get("roa")),
                "ros":  _safe_float(best.get("ros")),
                "beta": _safe_float(best.get("beta")),
            })

    # ── Giao dịch ngoại theo ngày ─────────────────────────────────
    # TCBS có endpoint thống kê ngoại hàng ngày
    foreign_data = _tcbs_get("/stock-insight/v1/stock/trade-stats", params={
        "ticker": symbol.upper(),
        "startDate": target_date.strftime("%Y-%m-%d"),
        "endDate":   target_date.strftime("%Y-%m-%d"),
    })
    if foreign_data and isinstance(foreign_data, dict):
        items = foreign_data.get("data", [])
        if items:
            row = items[0]
            buy  = _safe_float(row.get("foreignBuyVolume") or row.get("buyForeignVolume"))
            sell = _safe_float(row.get("foreignSellVolume") or row.get("sellForeignVolume"))
            result.update({
                "foreign_buy":  buy,
                "foreign_sell": sell,
                "foreign_net":  (buy - sell) if (buy is not None and sell is not None) else None,
            })

    return result


def _find_closest_quarterly(items: list, target: date) -> dict | None:
    """Tìm bản ghi quý gần nhất (không vượt quá) so với target_date."""
    best = None
    best_delta = None
    for item in items:
        q_str = item.get("reportDate") or item.get("yearReport", "")
        try:
            q_date = datetime.strptime(str(q_str)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if q_date > target:
            continue
        delta = (target - q_date).days
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = item
    return best


# ═══════════════════════════════════════════════════════
# 6. NGUỒN 3 – SSI iBoard API (miễn phí)
#    Lấy: bid_volume, ask_volume, foreign (backup)
#    Endpoint công khai của SSI không yêu cầu auth
# ═══════════════════════════════════════════════════════

_SSI_BASE = "https://iboard-query.ssi.com.vn"


def _ssi_get(path: str, params: dict | None = None) -> dict | list | None:
    url = f"{_SSI_BASE}{path}"
    try:
        r = _session.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"SSI API lỗi [{path}]: {e}")
        return None


def fetch_ssi_intraday(symbol: str, target_date: date) -> dict:
    """
    Lấy dữ liệu khớp lệnh và ngoại từ SSI iBoard.
    Chỉ có dữ liệu cho ngày trong phạm vi lưu trữ SSI (~60 ngày).
    Trả về dict bid_volume, ask_volume, foreign_buy, foreign_sell, foreign_net
    """
    result: dict = {}

    # SSI daily stock stat
    data = _ssi_get("/v2/stock-price/stock-price", params={
        "symbol":    symbol.upper(),
        "startDate": target_date.strftime("%Y-%m-%d"),
        "endDate":   target_date.strftime("%Y-%m-%d"),
        "pageIndex": 1,
        "pageSize":  1,
        "language":  "vi",
    })

    if data and isinstance(data, dict):
        rows = (
            data.get("data", {}).get("stockPrices")
            or data.get("data", [])
        )
        if rows and isinstance(rows, list):
            row = rows[0]
            buy  = _safe_float(row.get("foreignBuyVolume") or row.get("foreignBuyTrade"))
            sell = _safe_float(row.get("foreignSellVolume") or row.get("foreignSellTrade"))
            result.update({
                "bid_volume":  _safe_float(row.get("totalBidVolume") or row.get("buyVolume")),
                "ask_volume":  _safe_float(row.get("totalOfferVolume") or row.get("sellVolume")),
                "foreign_buy":  buy,
                "foreign_sell": sell,
                "foreign_net":  (buy - sell) if (buy is not None and sell is not None) else None,
            })

    return result


# ═══════════════════════════════════════════════════════
# 7. MERGE: kết hợp 3 nguồn với ưu tiên rõ ràng
# ═══════════════════════════════════════════════════════

# Mapping: field_name → [source_key_ưu_tiên_1, source_key_ưu_tiên_2, ...]
# Mỗi value là tuple (dict_nguồn, key_trong_dict_đó) — xem hàm merge bên dưới
FIELD_PRIORITY: dict[str, list[str]] = {
    # OHLCV – Vietstock là nguồn chính, TCBS là fallback
    "open_price":           ["vietstock", "tcbs_price"],
    "high_price":           ["vietstock", "tcbs_price"],
    "low_price":            ["vietstock", "tcbs_price"],
    "close_price":          ["vietstock", "tcbs_price"],
    "volume":               ["vietstock", "tcbs_price"],
    "market_cap":           ["vietstock"],
    "price_change":         ["vietstock"],
    "price_change_percent": ["vietstock"],
    # Chỉ số tài chính – TCBS API có lịch sử, Vietstock chỉ có hiện tại
    "eps":        ["tcbs_fin", "vietstock"],
    "pe":         ["tcbs_fin", "vietstock"],
    "forward_pe": ["vietstock"],
    "bvps":       ["vietstock"],
    "pb":         ["tcbs_fin", "vietstock"],
    "beta":       ["tcbs_fin", "vietstock"],
    "roe":        ["tcbs_fin", "vietstock"],
    "roaa":       ["tcbs_fin", "vietstock"],
    "ros":        ["tcbs_fin", "vietstock"],
    # Khối lượng đặt lệnh – SSI tốt nhất, Vietstock backup (chỉ hôm nay)
    "bid_volume": ["ssi", "vietstock"],
    "ask_volume": ["ssi", "vietstock"],
    # Giao dịch ngoại – TCBS hoặc SSI, Vietstock backup
    "foreign_buy":  ["tcbs_fin", "ssi", "vietstock"],
    "foreign_sell": ["tcbs_fin", "ssi", "vietstock"],
    "foreign_net":  ["tcbs_fin", "ssi", "vietstock"],
}


def merge_sources(
    vietstock: dict,
    tcbs_price: dict,
    tcbs_fin: dict,
    ssi: dict,
) -> dict:
    """
    Kết hợp dữ liệu từ các nguồn theo bảng FIELD_PRIORITY.
    Luôn ưu tiên nguồn đầu tiên có giá trị không None.
    """
    sources = {
        "vietstock":  vietstock,
        "tcbs_price": tcbs_price,
        "tcbs_fin":   tcbs_fin,
        "ssi":        ssi,
    }
    merged: dict = {}
    for field, priority in FIELD_PRIORITY.items():
        merged[field] = None
        for src_name in priority:
            val = sources.get(src_name, {}).get(field)
            if val is not None:
                merged[field] = val
                break
    return merged


# ═══════════════════════════════════════════════════════
# 8. CRAWL MỘT MÃ (orchestrator)
# ═══════════════════════════════════════════════════════
def crawl_single_stock(
    symbol: str,
    target_date: date,
    browser: VietstockBrowser,
    slug: str,
    profile_url: str,
    stats_url: str,
) -> Optional[dict]:
    """
    Crawl đầy đủ dữ liệu cho một mã cổ phiếu từ tất cả nguồn.
    Trả về dict đã merge, hoặc None nếu không có dữ liệu OHLCV cơ bản.
    """
    # Nguồn 1: Vietstock
    vs_data: dict = {}
    try:
        vs_data = fetch_vietstock(symbol, target_date, browser, slug, profile_url, stats_url)
    except Exception as e:
        logger.warning(f"  [{symbol}] Vietstock lỗi: {e}")

    # Nguồn 2a: TCBS giá lịch sử
    tcbs_price: dict = {}
    try:
        tcbs_price = fetch_tcbs_historical_price(symbol, target_date)
        if tcbs_price:
            logger.debug(f"  [{symbol}] TCBS price OK")
    except Exception as e:
        logger.debug(f"  [{symbol}] TCBS price lỗi: {e}")

    # Nguồn 2b: TCBS chỉ số tài chính
    tcbs_fin: dict = {}
    try:
        tcbs_fin = fetch_tcbs_financials(symbol, target_date)
        if tcbs_fin:
            logger.debug(f"  [{symbol}] TCBS fin OK: {list(k for k,v in tcbs_fin.items() if v is not None)}")
    except Exception as e:
        logger.debug(f"  [{symbol}] TCBS fin lỗi: {e}")

    # Nguồn 3: SSI
    ssi_data: dict = {}
    try:
        ssi_data = fetch_ssi_intraday(symbol, target_date)
        if ssi_data:
            logger.debug(f"  [{symbol}] SSI OK")
    except Exception as e:
        logger.debug(f"  [{symbol}] SSI lỗi: {e}")

    # Merge
    merged = merge_sources(vs_data, tcbs_price, tcbs_fin, ssi_data)

    # Bắt buộc phải có close_price mới tính là có dữ liệu
    if merged.get("close_price") is None:
        return None

    # Log coverage
    none_fields = [k for k, v in merged.items() if v is None]
    if none_fields:
        logger.debug(f"  [{symbol}] Trường còn None: {none_fields}")

    return merged


# ═══════════════════════════════════════════════════════
# 9. MAP SANG SCHEMA + UPSERT
# ═══════════════════════════════════════════════════════
def map_to_fact_market_price(
    raw: dict,
    stock_id: ObjectId,
    market_id: ObjectId,
    industry_id: Optional[ObjectId],
    data_source_id: ObjectId,
    time_id: int,
) -> dict:
    now = datetime.utcnow()
    return {
        "stock_id":       stock_id,
        "market_id":      market_id,
        "industry_id":    industry_id,
        "data_source_id": data_source_id,
        "time_id":        time_id,

        "open_price":  raw.get("open_price"),
        "high_price":  raw.get("high_price"),
        "low_price":   raw.get("low_price"),
        "close_price": raw.get("close_price"),
        "volume":      raw.get("volume"),

        "bid_volume":  raw.get("bid_volume"),
        "ask_volume":  raw.get("ask_volume"),

        "foreign_buy":  raw.get("foreign_buy"),
        "foreign_sell": raw.get("foreign_sell"),
        "foreign_net":  raw.get("foreign_net"),

        "market_cap":  raw.get("market_cap"),

        "eps":        raw.get("eps"),
        "pe":         raw.get("pe"),
        "forward_pe": raw.get("forward_pe"),
        "bvps":       raw.get("bvps"),
        "pb":         raw.get("pb"),
        "beta":       raw.get("beta"),
        "ros":        raw.get("ros"),
        "roe":        raw.get("roe"),
        "roaa":       raw.get("roaa"),

        "price_change":         raw.get("price_change"),
        "price_change_percent": raw.get("price_change_percent"),

        "crawled_at": now,
        "updated_at": now,
    }


def upsert_fact_market_price(db, doc: dict) -> tuple[int, int]:
    col = db[COL_FACT_MARKET_PRICES]
    filter_q = {
        "stock_id":       doc["stock_id"],
        "time_id":        doc["time_id"],
        "data_source_id": doc["data_source_id"],
    }
    created_at = doc.pop("created_at", datetime.utcnow())
    result = col.update_one(
        filter_q,
        {"$set": doc, "$setOnInsert": {"created_at": created_at}},
        upsert=True,
    )
    if result.upserted_id:
        return 1, 0
    if result.modified_count > 0:
        return 0, 1
    return 0, 0


# ═══════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════
def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(float(v)) if v is not None else None
    except (ValueError, TypeError):
        return None


def _get_or_create_stock_datasource(db, stock_id, symbol, is_dry_run) -> tuple[str, str, ObjectId]:
    """Trả về (profile_url, stats_url, stock_ds_id)."""
    ds_col = db["dimStockDataSources"]
    ds = ds_col.find_one({"stock_id": stock_id})
    if ds:
        return (
            ds.get("market_price_data_url", ""),
            ds.get("trade_stats_url", ""),
            ds["_id"],
        )
    sl = symbol.lower()
    new_ds = {
        "stock_id": stock_id,
        "trade_stats_url":      f"https://finance.vietstock.vn/{sl}/thong-ke-giao-dich.htm",
        "market_price_data_url":f"https://finance.vietstock.vn/{sl}-profile.htm",
        "financial_data_url":   f"https://finance.vietstock.vn/{sl}-profile.htm",
        "description": f"Auto-created for {symbol}",
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    if not is_dry_run:
        res = ds_col.insert_one(new_ds)
        ds_id = res.inserted_id
    else:
        ds_id = ObjectId()
    logger.info(f"  [{symbol}] 🔌 Tự động tạo stock data source ({ds_id})")
    return new_ds["market_price_data_url"], new_ds["trade_stats_url"], ds_id


# ═══════════════════════════════════════════════════════
# 10. MAIN
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Crawl thủ công dữ liệu HOSE theo ngày (multi-source).")
    parser.add_argument("--date",    required=True, help="Ngày YYYY-MM-DD")
    parser.add_argument("--source",  default=DATA_SOURCE_NAME)
    parser.add_argument("--delay",   type=float, default=0.5, help="Delay giữa các mã (giây)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit",   type=int, default=0, help="Giới hạn số mã (0 = không giới hạn)")
    args = parser.parse_args()

    target_date  = parse_date(args.date)
    is_dry_run   = args.dry_run
    req_delay    = args.delay

    if is_dry_run:
        logger.info("🔍 DRY RUN MODE – sẽ không lưu vào database")

    client, db = connect_mongodb()

    try:
        data_source_id = get_or_create_data_source(db, args.source) if not is_dry_run else ObjectId()
        time_id        = get_or_create_dim_time(db, target_date)    if not is_dry_run else date_to_time_id(target_date)
        stocks         = get_active_hose_stocks(db)

        if not stocks:
            logger.error("❌ Không có mã cổ phiếu nào trong DB. Seed dữ liệu trước.")
            sys.exit(1)

        if args.limit > 0:
            stocks = stocks[:args.limit]
            logger.info(f"🔧 Giới hạn: {len(stocks)} mã")

        crawl_log_id = create_crawl_log(db, time_id) if not is_dry_run else ObjectId()
        hose_market  = db[COL_DIM_MARKETS].find_one({"code": "HOSE"})
        hose_id      = hose_market["_id"] if hose_market else None

        total = len(stocks)
        cnt = {"fetched": 0, "inserted": 0, "updated": 0, "failed": 0, "skipped": 0}

        logger.info(f"\n{'═'*60}")
        logger.info(f"🚀 Bắt đầu crawl {total} mã – ngày {target_date}")
        logger.info(f"{'═'*60}\n")

        with VietstockBrowser() as browser:
            for idx, stock in enumerate(stocks, start=1):
                symbol      = stock.get("symbol", "???")
                stock_id    = stock["_id"]
                market_id   = stock.get("market_id") or hose_id
                industry_id = stock.get("industry_id")
                slug        = stock.get("slug") or symbol.lower()

                logger.info(f"[{idx}/{total}] ▶ {symbol}")

                try:
                    profile_url, stats_url, ds_id = _get_or_create_stock_datasource(
                        db, stock_id, symbol, is_dry_run
                    )

                    if not profile_url:
                        logger.warning(f"  [{symbol}] Thiếu profile_url → SKIPPED")
                        cnt["skipped"] += 1
                        if not is_dry_run:
                            write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "SKIPPED", "Missing profile_url")
                        continue

                    raw = crawl_single_stock(symbol, target_date, browser, slug, profile_url, stats_url)

                    if raw is None:
                        logger.warning(f"  [{symbol}] Không có dữ liệu ngày {target_date} → SKIPPED")
                        cnt["skipped"] += 1
                        if not is_dry_run:
                            write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "SKIPPED",
                                                   f"No data for {target_date}")
                        continue

                    cnt["fetched"] += 1

                    # Tóm tắt coverage
                    filled   = sum(1 for v in raw.values() if v is not None)
                    total_f  = len(raw)
                    coverage = f"{filled}/{total_f} trường"

                    if is_dry_run:
                        logger.info(f"  [{symbol}] ✅ [DRY RUN] {coverage} | close={raw.get('close_price')}")
                        cnt["inserted"] += 1
                        continue

                    fact_doc = map_to_fact_market_price(
                        raw, stock_id, market_id, industry_id, ds_id, time_id
                    )
                    ins, upd = upsert_fact_market_price(db, fact_doc)
                    cnt["inserted"] += ins
                    cnt["updated"]  += upd

                    action = "INSERT" if ins else ("UPDATE" if upd else "UNCHANGED")
                    logger.info(f"  [{symbol}] ✅ {action} | {coverage} | close={raw.get('close_price')}")

                    write_crawl_log_detail(
                        db, crawl_log_id, stock_id, symbol, "SUCCESS",
                        f"{action}: {coverage}, close={raw.get('close_price')}, vol={raw.get('volume')}",
                    )

                except Exception as exc:
                    cnt["failed"] += 1
                    logger.error(f"  [{symbol}] ❌ FAILED: {exc}")
                    if not is_dry_run:
                        write_crawl_log_detail(db, crawl_log_id, stock_id, symbol, "FAILED", str(exc)[:500])

                if req_delay > 0 and idx < total:
                    time.sleep(req_delay)

        # Xác định trạng thái cuối
        if cnt["failed"] == 0 and cnt["fetched"] > 0:
            final_status = "SUCCESS"
        elif cnt["fetched"] == 0 and cnt["failed"] == 0:
            final_status = "FAILED"
        elif cnt["failed"] > 0 and (cnt["inserted"] + cnt["updated"]) == 0:
            final_status = "FAILED"
        elif cnt["failed"] > 0:
            final_status = "PARTIAL_SUCCESS"
        else:
            final_status = "SUCCESS"

        logger.info(f"\n{'═'*60}")
        logger.info(f"📋 KẾT QUẢ CRAWL NGÀY {target_date}")
        logger.info(f"{'═'*60}")
        logger.info(f"  Tổng số mã      : {total}")
        logger.info(f"  Crawl OK        : {cnt['fetched']}")
        logger.info(f"  Skipped         : {cnt['skipped']}")
        logger.info(f"  Lỗi             : {cnt['failed']}")
        logger.info(f"  Insert mới      : {cnt['inserted']}")
        logger.info(f"  Cập nhật        : {cnt['updated']}")
        logger.info(f"  Trạng thái      : {final_status}")
        logger.info(f"{'═'*60}\n")

        if not is_dry_run:
            finalize_crawl_log(
                db, crawl_log_id,
                cnt["fetched"], cnt["inserted"], cnt["updated"], cnt["failed"], cnt["skipped"],
                final_status,
            )
            write_fact_crawl_quality(
                db, data_source_id, hose_id, time_id,
                cnt["fetched"], cnt["inserted"], cnt["updated"], cnt["failed"],
                final_status,
            )

    finally:
        client.close()
        logger.info("🔒 Đã đóng kết nối MongoDB")


if __name__ == "__main__":
    main()