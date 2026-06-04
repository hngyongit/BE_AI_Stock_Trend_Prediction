"""
manual_crawl_by_date.py
-----------------------
Script crawl thủ công dữ liệu chứng khoán theo ngày bất kỳ.

Cách dùng:
    python manual_crawl_by_date.py --date 2026-05-22
    python manual_crawl_by_date.py --date 2026-05-22 --source vnstock
    python manual_crawl_by_date.py --date 2026-05-22 --delay 0.3 --dry-run

Yêu cầu file .env cùng thư mục có:
    MONGODB_URI=...
    MONGODB_DB_NAME=...  (tuỳ chọn, mặc định lấy từ URI)
"""

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

# Setup path to import vietstock_crawler
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vietstock_crawler.core.browser import VietstockBrowser
from vietstock_crawler.services.vietstock_service import crawl_company
from vietstock_crawler.utils.url_utils import normalize_slug_value
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# Fix Unicode / emoji cho Windows terminal (CP1258)
# ─────────────────────────────────────────────
import io
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
# Cấu hình logging
# ─────────────────────────────────────────────
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
DATA_SOURCE_NAME = "vietstock"
DATA_SOURCE_PROVIDER_TYPE = "browser_crawler"
DATA_SOURCE_DESCRIPTION = "Playwright crawler cào dữ liệu từ Vietstock Finance"

# MongoDB collection names (khớp với Mongoose schema)
COL_DIM_STOCKS = "dimstocks"
COL_DIM_TIMES = "dimTimes"
COL_DIM_DATA_SOURCES = "dimDataSources"
COL_DIM_MARKETS = "dimMarkets"
COL_FACT_MARKET_PRICES = "factMarketPrices"
COL_FACT_MARKET_OVERVIEWS = "factMarketOverviews"
COL_CRAWL_LOGS = "crawlLogs"
COL_CRAWL_LOG_DETAILS = "crawlLogDetails"
COL_FACT_CRAWL_QUALITIES = "factCrawlQualities"


# ═══════════════════════════════════════════════════════
# 1. KẾT NỐI MONGODB
# ═══════════════════════════════════════════════════════
def connect_mongodb():
    """
    Kết nối MongoDB từ biến môi trường MONGODB_URI.
    Trả về (client, db).
    """
    load_dotenv()

    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        logger.error("Không tìm thấy MONGODB_URI trong file .env")
        sys.exit(1)

    # MONGODB_DB_NAME tuỳ chọn – nếu không có thì dùng database mặc định từ URI
    db_name = os.getenv("MONGODB_DB_NAME")

    try:
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=10_000)
        # Kiểm tra kết nối
        client.admin.command("ping")

        if db_name:
            db = client[db_name]
        else:
            db = client.get_default_database()

        logger.info(f"✅ Kết nối MongoDB thành công. Database: {db.name}")
        return client, db
    except Exception as e:
        logger.error(f"❌ Không thể kết nối MongoDB: {e}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════
# 2. PARSE NGÀY ĐẦU VÀO
# ═══════════════════════════════════════════════════════
def parse_date(date_str: str) -> date:
    """
    Parse chuỗi ngày theo định dạng YYYY-MM-DD.
    Trả về datetime.date.
    """
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
        logger.info(f"📅 Ngày crawl: {parsed.strftime('%d/%m/%Y')}")
        return parsed
    except ValueError:
        logger.error(f"❌ Định dạng ngày không hợp lệ: '{date_str}'. Vui lòng dùng YYYY-MM-DD.")
        sys.exit(1)


def date_to_time_id(d: date) -> int:
    """
    Chuyển date thành time_id dạng số nguyên YYYYMMDD.
    Ví dụ: 2026-05-22 → 20260522
    """
    return int(d.strftime("%Y%m%d"))


# ═══════════════════════════════════════════════════════
# 3. LẤY DANH SÁCH CỔ PHIẾU TỪ dim_stocks
# ═══════════════════════════════════════════════════════
def get_active_hose_stocks(db) -> list[dict]:
    """
    Lấy toàn bộ cổ phiếu HOSE có status='ACTIVE' từ collection dimstocks.
    Trả về list[dict] với các key: _id, symbol, market_id, industry_id, slug.
    """
    market_col = db["dimMarkets"]
    hose_market = market_col.find_one({"code": "HOSE"})
    if not hose_market:
        logger.error("❌ Không tìm thấy HOSE market trong dimMarkets")
        return []

    col = db[COL_DIM_STOCKS]
    # Mongoose lưu status uppercase 'ACTIVE' (xem dim-stock.model.js)
    query = {
        "market_id": hose_market["_id"],
        "status": {"$in": ["ACTIVE", "active"]},  # hỗ trợ cả hai kiểu
    }
    stocks = list(col.find(query, {"_id": 1, "symbol": 1, "market_id": 1, "industry_id": 1, "slug": 1}))
    logger.info(f"📊 Tìm thấy {len(stocks)} mã cổ phiếu HOSE đang hoạt động")
    return stocks


# ═══════════════════════════════════════════════════════
# 4. TẠO / KIỂM TRA BẢN GHI TRONG dim_time
# ═══════════════════════════════════════════════════════
def get_or_create_dim_time(db, target_date: date) -> int:
    """
    Tìm hoặc tạo bản ghi trong dimTimes cho ngày crawl.
    Trả về time_id (YYYYMMDD dạng số).
    """
    col = db[COL_DIM_TIMES]
    time_id = date_to_time_id(target_date)

    existing = col.find_one({"time_id": time_id})
    if existing:
        logger.info(f"📆 dim_time đã tồn tại: time_id={time_id}")
        return time_id

    # Tính toán thông tin ngày
    import calendar
    year = target_date.year
    month = target_date.month
    day = target_date.day
    weekday = target_date.weekday()  # 0=Monday … 6=Sunday
    # Tuần trong năm theo ISO
    week_of_year = target_date.isocalendar()[1]
    quarter = (month - 1) // 3 + 1
    # Ngày giao dịch: thứ 2–6, loại trừ ngày nghỉ lễ (đơn giản hoá)
    is_trading_day = weekday < 5  # True nếu không phải T7/CN

    doc = {
        "time_id": time_id,
        "full_date": datetime(year, month, day, 0, 0, 0),
        "day": day,
        "month": month,
        "quarter": quarter,
        "year": year,
        "week_of_year": week_of_year,
        "weekday": weekday,
        "is_trading_day": is_trading_day,
        "created_at": datetime.utcnow(),
    }

    try:
        col.insert_one(doc)
        logger.info(f"📆 Đã tạo dim_time mới: time_id={time_id}, is_trading_day={is_trading_day}")
    except Exception:
        # Race condition: có thể record đã được tạo bởi process khác
        logger.warning(f"⚠️  dim_time time_id={time_id} có thể đã tồn tại (bỏ qua lỗi insert)")

    return time_id


# ═══════════════════════════════════════════════════════
# 5. TẠO / KIỂM TRA NGUỒN DỮ LIỆU TRONG dim_data_sources
# ═══════════════════════════════════════════════════════
def get_or_create_data_source(db, source_name: str = DATA_SOURCE_NAME) -> ObjectId:
    """
    Tìm hoặc tạo bản ghi nguồn dữ liệu trong dimDataSources.
    Trả về ObjectId của data source.
    """
    col = db[COL_DIM_DATA_SOURCES]
    existing = col.find_one({"name": source_name})

    if existing:
        logger.info(f"🔌 Data source '{source_name}' đã tồn tại: {existing['_id']}")
        return existing["_id"]

    doc = {
        "name": source_name,
        "provider_type": DATA_SOURCE_PROVIDER_TYPE,
        "base_url": "",
        "description": DATA_SOURCE_DESCRIPTION,
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = col.insert_one(doc)
    logger.info(f"🔌 Đã tạo data source mới: '{source_name}' ({result.inserted_id})")
    return result.inserted_id


# ═══════════════════════════════════════════════════════
# 6. TẠO CRAWL LOG (bắt đầu session)
# ═══════════════════════════════════════════════════════
def create_crawl_log(db, time_id: int) -> ObjectId:
    """
    Tạo một bản ghi crawl_log cho phiên crawl hiện tại.
    Trả về ObjectId của crawl log.
    """
    col = db[COL_CRAWL_LOGS]
    doc = {
        "crawl_job_id": None,  # manual crawl không có job định kỳ
        "started_at": datetime.utcnow(),
        "ended_at": None,
        "status": "PENDING",
        "records_fetched": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "records_failed": 0,
        "error_message": f"Manual crawl cho ngày time_id={time_id}",
        "created_at": datetime.utcnow(),
    }
    result = col.insert_one(doc)
    logger.info(f"📝 Tạo crawl_log: {result.inserted_id}")
    return result.inserted_id


# ═══════════════════════════════════════════════════════
# 7. GHI CRAWL LOG DETAIL (mỗi mã cổ phiếu)
# ═══════════════════════════════════════════════════════
def write_crawl_log_detail(
    db,
    crawl_log_id: ObjectId,
    stock_id: ObjectId,
    symbol: str,
    status: str,
    message: str = "",
    data_type: str = "market_price",
):
    """
    Ghi bản ghi chi tiết cho từng mã cổ phiếu vào crawlLogDetails.

    Parameters:
        status: 'SUCCESS' | 'FAILED' | 'SKIPPED'
        data_type: loại dữ liệu đã crawl
    """
    col = db[COL_CRAWL_LOG_DETAILS]
    doc = {
        "crawl_log_id": crawl_log_id,
        "stock_id": stock_id,
        "symbol": symbol,
        "data_type": data_type,
        "status": status,
        "message": message,
        "created_at": datetime.utcnow(),
    }
    col.insert_one(doc)


# ═══════════════════════════════════════════════════════
# 8. CẬP NHẬT CRAWL LOG (kết thúc session)
# ═══════════════════════════════════════════════════════
def finalize_crawl_log(
    db,
    crawl_log_id: ObjectId,
    records_fetched: int,
    records_inserted: int,
    records_updated: int,
    records_failed: int,
    records_skipped: int,
    status: str,
):
    """
    Cập nhật bản ghi crawl_log khi hoàn thành session.
    """
    col = db[COL_CRAWL_LOGS]
    update = {
        "$set": {
            "ended_at": datetime.utcnow(),
            "status": status,
            "records_fetched": records_fetched,
            "records_inserted": records_inserted,
            "records_updated": records_updated,
            "records_failed": records_failed,
            "error_message": f"Skipped: {records_skipped} mã không có dữ liệu",
        }
    }
    col.update_one({"_id": crawl_log_id}, update)
    logger.info(
        f"📝 Cập nhật crawl_log {crawl_log_id}: status={status}, "
        f"fetched={records_fetched}, inserted={records_inserted}, "
        f"updated={records_updated}, failed={records_failed}, skipped={records_skipped}"
    )


# ═══════════════════════════════════════════════════════
# 9. GHI FACT CRAWL QUALITY
# ═══════════════════════════════════════════════════════
def write_fact_crawl_quality(
    db,
    data_source_id: ObjectId,
    market_id: ObjectId | None,
    time_id: int,
    records_fetched: int,
    records_inserted: int,
    records_updated: int,
    records_failed: int,
    status: str,
):
    """
    Ghi hoặc cập nhật bản ghi chất lượng crawl vào factCrawlQualities.
    """
    col = db[COL_FACT_CRAWL_QUALITIES]
    total_processed = records_inserted + records_updated + records_failed
    success_rate = (
        round((records_inserted + records_updated) / total_processed * 100, 2)
        if total_processed > 0
        else 0.0
    )

    doc = {
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
        "created_at": datetime.utcnow(),
    }
    col.insert_one(doc)
    logger.info(
        f"📊 Ghi fact_crawl_quality: status={status}, success_rate={success_rate}%, "
        f"time_id={time_id}"
    )


def extract_historical_price_from_trading_stats(html: str, target_date: date) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    
    # Target date formats: DD/MM/YYYY, D/M/YYYY, DD/MM/YY
    target_date_str = target_date.strftime("%d/%m/%Y")
    target_date_str_short = f"{target_date.day}/{target_date.month}/{target_date.year}"
    target_date_str_yy = target_date.strftime("%d/%m/%y")
    date_options = {target_date_str, target_date_str_short, target_date_str_yy}
    
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 12: # Expect at least 12 columns
                continue
            date_cell = cells[1].strip() # Date is in column 1 (0-indexed 1)
            if date_cell in date_options:
                from vietstock_crawler.utils.number_utils import normalize_number
                
                close_val = normalize_number(cells[5])
                open_val = normalize_number(cells[4])
                high_val = normalize_number(cells[6])
                low_val = normalize_number(cells[7])
                ref_val = normalize_number(cells[3])
                
                # Volume khớp lệnh (triệu CP) -> multiply by 1,000,000
                vol_val = normalize_number(cells[11])
                if vol_val is not None:
                    vol_val = int(vol_val * 1_000_000)
                    
                # Vốn hóa (tỷ đồng) -> multiply by 1,000,000,000
                mc_val = normalize_number(cells[17])
                if mc_val is not None:
                    mc_val = mc_val * 1_000_000_000
                    
                # Price change
                pc_val = normalize_number(cells[9])
                pc_pct = normalize_number(cells[10])
                
                return {
                    "open": open_val,
                    "high": high_val,
                    "low": low_val,
                    "close": close_val,
                    "reference": ref_val,
                    "volume": vol_val,
                    "market_cap": mc_val,
                    "price_change": pc_val,
                    "price_change_percent": pc_pct,
                }
    return None


def crawl_stock_data(symbol: str, target_date: date, browser: VietstockBrowser, slug: str, profile_url: str, stats_url: str) -> dict | None:
    """
    Crawl dữ liệu cổ phiếu bằng Playwright từ Vietstock.
    Tương tự như crawler chính.
    """
    try:
        is_today = (target_date == date.today())
        
        # 1. Cào trang profile chính để lấy định giá & chỉ số tài chính cơ bản
        enable_financial = os.getenv("ENABLE_FINANCIAL_DATA", "false").lower() == "true"
        market, financial = crawl_company(
            symbol=symbol,
            slug=slug,
            browser=browser,
            profile_url=profile_url,
            crawl_financial=enable_financial
        )
        
        if market.get("error") or not market.get("is_valid_url"):
            raise RuntimeError(market.get("error") or "Không tải được trang profile")
            
        # 2. Cào trang thống kê giao dịch để tìm giá lịch sử của target_date
        if not stats_url or "finance.vietstock.vn" not in stats_url:
            stats_url = f"https://finance.vietstock.vn/{symbol.upper()}/thong-ke-giao-dich.htm"
        html = browser.get_html(stats_url)
        
        hist_data = extract_historical_price_from_trading_stats(html, target_date)
        if not hist_data:
            return None
            
        # 3. Tổng hợp dữ liệu
        result = {
            "open_price": hist_data["open"],
            "high_price": hist_data["high"],
            "low_price": hist_data["low"],
            "close_price": hist_data["close"],
            "volume": hist_data["volume"],
            "market_cap": hist_data["market_cap"],
            "price_change": hist_data["price_change"],
            "price_change_percent": hist_data["price_change_percent"],
            
            # Chỉ số tài chính lấy từ profile
            "eps": market.get("eps"),
            "pe": market.get("pe"),
            "forward_pe": market.get("forward_pe"),
            "bvps": market.get("bvps"),
            "pb": market.get("pb"),
            "beta": market.get("beta"),
            "roe": market.get("roe"),
            "roaa": market.get("roaa"),
            "ros": financial.get("ros"),
        }
        
        # Khối lượng mua bán khớp lệnh & nước ngoài chỉ lấy khi crawl hôm nay
        if is_today:
            result.update({
                "bid_volume": market.get("bid_volume"),
                "ask_volume": market.get("ask_volume"),
                "foreign_buy": market.get("foreign_buy"),
                "foreign_sell": market.get("foreign_sell"),
                "foreign_net": market.get("foreign_net"),
            })
        else:
            result.update({
                "bid_volume": None,
                "ask_volume": None,
                "foreign_buy": None,
                "foreign_sell": None,
                "foreign_net": None,
            })
            
        return result
        
    except Exception as e:
        logger.error(f"  [{symbol}] Lỗi khi cào dữ liệu Playwright: {e}")
        raise


# ═══════════════════════════════════════════════════════
# 11. MAPPING VÀ UPSERT VÀO fact_market_prices
# ═══════════════════════════════════════════════════════
def map_to_fact_market_price(
    raw_data: dict,
    stock_id: ObjectId,
    market_id: ObjectId,
    industry_id: ObjectId | None,
    data_source_id: ObjectId,
    time_id: int,
) -> dict:
    """
    Map dữ liệu crawl thô sang document schema của factMarketPrices.
    """
    now = datetime.utcnow()
    return {
        # Khoá ngoại
        "stock_id": stock_id,
        "market_id": market_id,
        "industry_id": industry_id,
        "data_source_id": data_source_id,
        "time_id": time_id,

        # Giá OHLCV (bắt buộc)
        "open_price": raw_data.get("open_price"),
        "high_price": raw_data.get("high_price"),
        "low_price": raw_data.get("low_price"),
        "close_price": raw_data.get("close_price"),
        "volume": raw_data.get("volume"),

        # Khối lượng đặt lệnh
        "bid_volume": raw_data.get("bid_volume"),
        "ask_volume": raw_data.get("ask_volume"),

        # Giao dịch ngoại
        "foreign_buy": raw_data.get("foreign_buy"),
        "foreign_sell": raw_data.get("foreign_sell"),
        "foreign_net": raw_data.get("foreign_net"),

        # Vốn hoá
        "market_cap": raw_data.get("market_cap"),

        # Chỉ số định giá & tài chính
        "eps": raw_data.get("eps"),
        "pe": raw_data.get("pe"),
        "forward_pe": raw_data.get("forward_pe"),
        "bvps": raw_data.get("bvps"),
        "pb": raw_data.get("pb"),
        "beta": raw_data.get("beta"),
        "ros": raw_data.get("ros"),
        "roe": raw_data.get("roe"),
        "roaa": raw_data.get("roaa"),

        # Biến động giá
        "price_change": raw_data.get("price_change"),
        "price_change_percent": raw_data.get("price_change_percent"),

        # Metadata
        "crawled_at": now,
        "updated_at": now,
    }


def upsert_fact_market_price(db, doc: dict) -> tuple[int, int]:
    """
    Upsert document vào factMarketPrices theo unique key:
        stock_id + time_id + data_source_id

    Trả về (inserted, updated) — mỗi giá trị là 0 hoặc 1.
    """
    col = db[COL_FACT_MARKET_PRICES]
    filter_query = {
        "stock_id": doc["stock_id"],
        "time_id": doc["time_id"],
        "data_source_id": doc["data_source_id"],
    }

    # Tách created_at ra khỏi $set để tránh ghi đè
    created_at = doc.pop("created_at", datetime.utcnow())

    result = col.update_one(
        filter_query,
        {
            "$set": doc,
            "$setOnInsert": {"created_at": created_at},
        },
        upsert=True,
    )

    if result.upserted_id:
        return 1, 0  # inserted
    elif result.modified_count > 0:
        return 0, 1  # updated
    else:
        return 0, 0  # không thay đổi (dữ liệu giống hệt)


# Các hàm helper vnstock cũ đã được xóa bỏ để sử dụng bộ Playwright tương ứng.


# ═══════════════════════════════════════════════════════
# 12. MAIN FUNCTION
# ═══════════════════════════════════════════════════════
def main():
    # ── Parse arguments ──
    parser = argparse.ArgumentParser(
        description="Crawl thủ công dữ liệu chứng khoán HOSE theo ngày bất kỳ."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Ngày crawl theo định dạng YYYY-MM-DD. Ví dụ: 2026-05-22",
    )
    parser.add_argument(
        "--source",
        default=DATA_SOURCE_NAME,
        help=f"Tên data source (mặc định: {DATA_SOURCE_NAME})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Thời gian chờ giữa các mã cổ phiếu (giây, mặc định: 0.5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chạy thử – crawl dữ liệu nhưng KHÔNG lưu vào database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Giới hạn số mã crawl (0 = không giới hạn, dùng để test)",
    )
    args = parser.parse_args()

    # ── Parse ngày ──
    target_date = parse_date(args.date)
    is_dry_run = args.dry_run
    request_delay = args.delay

    if is_dry_run:
        logger.info("🔍 DRY RUN MODE – sẽ không lưu dữ liệu vào database")

    # ── Kết nối MongoDB ──
    client, db = connect_mongodb()

    try:
        # ── Lấy dim_data_source ──
        data_source_id = get_or_create_data_source(db, args.source) if not is_dry_run else ObjectId()

        # ── Lấy time_id ──
        time_id = get_or_create_dim_time(db, target_date) if not is_dry_run else date_to_time_id(target_date)

        # ── Lấy danh sách cổ phiếu ──
        stocks = get_active_hose_stocks(db)
        if not stocks:
            logger.error("❌ Không tìm thấy mã cổ phiếu nào trong database. Hãy seed dữ liệu trước.")
            sys.exit(1)

        # Giới hạn số mã nếu có --limit
        if args.limit > 0:
            stocks = stocks[: args.limit]
            logger.info(f"🔧 Giới hạn test: chỉ crawl {len(stocks)} mã đầu tiên")

        # ── Tạo crawl log ──
        crawl_log_id = create_crawl_log(db, time_id) if not is_dry_run else ObjectId()

        # ── Lấy market_id của HOSE (dùng chung) ──
        hose_market = db[COL_DIM_MARKETS].find_one({"code": "HOSE"})
        hose_market_id = hose_market["_id"] if hose_market else None

        # ── Counters ──
        total = len(stocks)
        cnt_fetched = 0
        cnt_inserted = 0
        cnt_updated = 0
        cnt_failed = 0
        cnt_skipped = 0

        logger.info(f"\n{'═'*60}")
        logger.info(f"🚀 Bắt đầu crawl {total} mã cổ phiếu HOSE ngày {target_date}")
        logger.info(f"{'═'*60}\n")

        # ── Vòng lặp crawl từng mã sử dụng Playwright ──
        with VietstockBrowser() as browser:
            for idx, stock in enumerate(stocks, start=1):
                symbol = stock.get("symbol", "???")
                stock_id = stock["_id"]
                market_id = stock.get("market_id") or hose_market_id
                industry_id = stock.get("industry_id")
                slug = stock.get("slug") or symbol.lower()

                logger.info(f"[{idx}/{total}] ▶ {symbol} ...")

                try:
                    # Retrieve or create stock data source details from DB
                    ds_col = db["dimStockDataSources"]
                    ds = ds_col.find_one({"stock_id": stock_id})
                    
                    market_price_data_url = ""
                    stock_data_source_id = None
                    trade_stats_url = ""
                    
                    if ds:
                        market_price_data_url = ds.get("market_price_data_url", "")
                        stock_data_source_id = ds["_id"]
                        trade_stats_url = ds.get("trade_stats_url", "")
                    else:
                        # Auto-create stock data source if missing to avoid bootstrap failures
                        symbol_lower = symbol.lower()
                        new_ds = {
                            "stock_id": stock_id,
                            "trade_stats_url": f"https://finance.vietstock.vn/{symbol_lower}/thong-ke-giao-dich.htm",
                            "market_price_data_url": f"https://finance.vietstock.vn/{symbol_lower}-profile.htm",
                            "financial_data_url": f"https://finance.vietstock.vn/{symbol_lower}-profile.htm",
                            "description": f"Vietstock crawl URLs for {symbol}",
                            "status": "active",
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                        if not is_dry_run:
                            res = ds_col.insert_one(new_ds)
                            stock_data_source_id = res.inserted_id
                        else:
                            stock_data_source_id = ObjectId()
                        market_price_data_url = new_ds["market_price_data_url"]
                        trade_stats_url = new_ds["trade_stats_url"]
                        logger.info(f"  [{symbol}] 🔌 Tự động tạo stock data source mới (ID: {stock_data_source_id})")

                    # Skip crawling if market_price_data_url is empty/null
                    if not market_price_data_url:
                        logger.warning(f"  [{symbol}] Missing market_price_data_url -> SKIPPED")
                        cnt_skipped += 1
                        if not is_dry_run:
                            write_crawl_log_detail(
                                db, crawl_log_id, stock_id, symbol,
                                status="SKIPPED",
                                message="Missing market_price_data_url",
                            )
                        continue

                    # Use stock-specific data_source_id as the primary data_source_id for factMarketPrices
                    current_ds_id = stock_data_source_id or data_source_id

                    # ── Crawl dữ liệu ──
                    raw_data = crawl_stock_data(symbol, target_date, browser, slug, market_price_data_url, trade_stats_url)

                    if raw_data is None:
                        logger.warning(f"  [{symbol}] Không có dữ liệu cho ngày {target_date} → SKIPPED")
                        cnt_skipped += 1
                        if not is_dry_run:
                            write_crawl_log_detail(
                                db, crawl_log_id, stock_id, symbol,
                                status="SKIPPED",
                                message=f"Không có dữ liệu cho ngày {target_date}",
                            )
                        continue

                    cnt_fetched += 1

                    if is_dry_run:
                        logger.info(f"  [{symbol}] ✅ [DRY RUN] Dữ liệu: {raw_data}")
                        cnt_inserted += 1  # tính là sẽ insert
                        continue

                    # ── Map sang schema ──
                    fact_doc = map_to_fact_market_price(
                        raw_data=raw_data,
                        stock_id=stock_id,
                        market_id=market_id,
                        industry_id=industry_id,
                        data_source_id=current_ds_id,
                        time_id=time_id,
                    )

                    # ── Upsert vào DB ──
                    inserted, updated = upsert_fact_market_price(db, fact_doc)
                    cnt_inserted += inserted
                    cnt_updated += updated

                    action = "INSERT" if inserted else ("UPDATE" if updated else "UNCHANGED")
                    logger.info(f"  [{symbol}] ✅ {action}")

                    # ── Ghi log chi tiết ──
                    write_crawl_log_detail(
                        db, crawl_log_id, stock_id, symbol,
                        status="SUCCESS",
                        message=f"{action}: open={raw_data.get('open_price')}, close={raw_data.get('close_price')}, vol={raw_data.get('volume')}",
                    )

                except Exception as exc:
                    cnt_failed += 1
                    err_msg = str(exc)
                    logger.error(f"  [{symbol}] ❌ FAILED: {err_msg}")
                    if not is_dry_run:
                        write_crawl_log_detail(
                            db, crawl_log_id, stock_id, symbol,
                            status="FAILED",
                            message=err_msg[:500],  # giới hạn độ dài message
                        )

                # ── Delay giữa các mã ──
                if request_delay > 0 and idx < total:
                    time.sleep(request_delay)

        # ── Xác định trạng thái tổng ──
        if cnt_failed == 0 and cnt_fetched > 0:
            final_status = "SUCCESS"
        elif cnt_fetched == 0 and cnt_failed == 0:
            final_status = "FAILED"  # toàn bộ bị SKIPPED = không có dữ liệu
        elif cnt_failed > 0 and (cnt_inserted + cnt_updated) == 0:
            final_status = "FAILED"
        elif cnt_failed > 0:
            final_status = "PARTIAL_SUCCESS"
        else:
            final_status = "SUCCESS"

        # ── In tóm tắt ──
        logger.info(f"\n{'═'*60}")
        logger.info(f"📋 KẾT QUẢ CRAWL NGÀY {target_date}")
        logger.info(f"{'═'*60}")
        logger.info(f"  Tổng số mã        : {total}")
        logger.info(f"  Crawl thành công  : {cnt_fetched}")
        logger.info(f"  Bỏ qua (no data)  : {cnt_skipped}")
        logger.info(f"  Lỗi               : {cnt_failed}")
        logger.info(f"  Insert mới        : {cnt_inserted}")
        logger.info(f"  Cập nhật          : {cnt_updated}")
        logger.info(f"  Trạng thái        : {final_status}")
        logger.info(f"{'═'*60}\n")

        if not is_dry_run:
            # ── Finalize crawl_log ──
            finalize_crawl_log(
                db=db,
                crawl_log_id=crawl_log_id,
                records_fetched=cnt_fetched,
                records_inserted=cnt_inserted,
                records_updated=cnt_updated,
                records_failed=cnt_failed,
                records_skipped=cnt_skipped,
                status=final_status,
            )

            # ── Ghi fact_crawl_quality ──
            write_fact_crawl_quality(
                db=db,
                data_source_id=data_source_id,
                market_id=hose_market_id,
                time_id=time_id,
                records_fetched=cnt_fetched,
                records_inserted=cnt_inserted,
                records_updated=cnt_updated,
                records_failed=cnt_failed,
                status=final_status,
            )

    finally:
        client.close()
        logger.info("🔒 Đã đóng kết nối MongoDB")


# ═══════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    main()
