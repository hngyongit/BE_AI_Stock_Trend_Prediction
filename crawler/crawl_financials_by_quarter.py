"""
crawl_financials_by_quarter.py
------------------------------
Script crawl thủ công báo cáo tài chính theo quý từ Vietstock, giới hạn lấy 6 quý gần nhất.
Lưu vào collection `factFinancialStatements` trên MongoDB.

Cách dùng:
    python crawl_financials_by_quarter.py --symbols FPT,HPG
    python crawl_financials_by_quarter.py --limit 5
    python crawl_financials_by_quarter.py --symbols FPT --dry-run
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from bson import ObjectId
from dotenv import load_dotenv

# Setup path to import vietstock_crawler
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vietstock_crawler.config.settings import get_settings
from vietstock_crawler.core.browser import VietstockBrowser
from vietstock_crawler.services.mongodb_service import MongoDBService
from vietstock_crawler.parsers.bctt_parser import crawl_bctt_all_quarters

# Fix Unicode / emoji cho Windows terminal
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Setup logging
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger(__name__)

# Constants
DATA_SOURCE_NAME = "vietstock"

def parse_quarter_key(period_str: str) -> tuple[int, int]:
    """Chuyển Q1/2026 thành (2026, 1) để sắp xếp giảm dần."""
    m = re.match(r"Q([1-4])/(\d{4})", period_str)
    if m:
        return int(m.group(2)), int(m.group(1))
    return 0, 0

def get_active_hose_stocks(db) -> list[dict[str, Any]]:
    hose_market = db["dimMarkets"].find_one({"code": {"$in": ["HOSE", "hose"]}})
    if not hose_market:
        logger.error("❌ Không tìm thấy HOSE market trong dimMarkets")
        return []

    query = {"market_id": hose_market["_id"], "status": {"$in": ["ACTIVE", "active"]}}
    projection = {"_id": 1, "symbol": 1, "slug": 1}
    stocks = list(db["dimstocks"].find(query, projection).sort("symbol", 1))
    logger.info(f"📊 Tìm thấy {len(stocks)} mã cổ phiếu HOSE active trong DB")
    return stocks

def main():
    parser = argparse.ArgumentParser(description="Crawl quarterly financial statements from Vietstock")
    parser.add_argument("--symbols", type=str, help="Danh sách mã cổ phiếu cách nhau bằng dấu phẩy, ví dụ: FPT,HPG")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số lượng mã cần crawl")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử nghiệm không ghi database")
    parser.add_argument("--delay", type=float, default=2.0, help="Thời gian nghỉ giữa các mã (giây)")
    args = parser.parse_args()

    load_dotenv()
    settings = get_settings()

    db_service = MongoDBService()
    if not db_service.is_connected():
        logger.error("❌ Không kết nối được MongoDB. Vui lòng kiểm tra lại MONGODB_URI.")
        sys.exit(1)

    db = db_service.db
    data_source_id = db_service.get_data_source_id(DATA_SOURCE_NAME)

    # Xác định danh sách stocks cần cào
    stocks_to_crawl = []
    if args.symbols:
        symbols_list = [sym.strip().upper() for sym in args.symbols.split(",") if sym.strip()]
        for sym in symbols_list:
            s_doc = db["dimstocks"].find_one({"symbol": sym})
            if s_doc:
                stocks_to_crawl.append(s_doc)
            else:
                # Tạo stock mới nếu chưa có
                hose = db["dimMarkets"].find_one({"code": "HOSE"})
                new_stock = {
                    "market_id": hose["_id"] if hose else None,
                    "industry_id": None,
                    "symbol": sym,
                    "company_name": sym,
                    "status": "ACTIVE",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                res = db["dimstocks"].insert_one(new_stock)
                new_stock["_id"] = res.inserted_id
                stocks_to_crawl.append(new_stock)
                logger.info(f"Tạo mới Stock {sym} (ID: {res.inserted_id})")
    else:
        stocks_to_crawl = get_active_hose_stocks(db)

    if args.limit > 0:
        stocks_to_crawl = stocks_to_crawl[:args.limit]

    total_stocks = len(stocks_to_crawl)
    logger.info(f"🚀 Bắt đầu crawl Báo Cáo Tài Chính Quý cho {total_stocks} mã cổ phiếu.")
    if args.dry_run:
        logger.info("🔍 CHẾ ĐỘ DRY-RUN: Chỉ hiển thị dữ liệu parsed, không lưu database.")

    # Khởi tạo Crawl Log
    log_id = None
    if not args.dry_run:
        log_id = db_service.create_crawl_log()
        db["crawlLogs"].update_one(
            {"_id": log_id},
            {"$set": {"error_message": f"Crawl BCTT quý cho {total_stocks} mã HOSE"}}
        )
        logger.info(f"[MongoDB] Đã tạo crawl log ID: {log_id}")

    records_fetched = 0
    records_inserted = 0
    records_updated = 0
    records_failed = 0

    with VietstockBrowser(timeout=settings.symbol_crawl_timeout) as browser:
        for idx, stock in enumerate(stocks_to_crawl, 1):
            symbol = stock["symbol"].upper()
            stock_id = stock["_id"]
            
            # Resolve data source details
            resolved_ds_id, _ = db_service.get_or_create_stock_data_source(stock_id, symbol)
            ds_id = resolved_ds_id or data_source_id

            logger.info(f"=== [{idx}/{total_stocks}] Crawling BCTT cho {symbol} ===")
            start_time = time.time()

            try:
                # Crawl all quarters
                periods_data = crawl_bctt_all_quarters(symbol, browser)
                if not periods_data:
                    raise RuntimeError("Không bóc tách được dữ liệu BCTT từ Vietstock.")

                # Sắp xếp các kỳ để lấy 6 quý gần nhất
                sorted_periods = sorted(periods_data.keys(), key=parse_quarter_key, reverse=True)
                target_periods = sorted_periods[:6]
                logger.info(f"  [{symbol}] Quét được {len(sorted_periods)} quý. Lấy 6 quý gần nhất: {target_periods}")

                # Lưu từng quý
                for period_name in target_periods:
                    metrics = periods_data[period_name]
                    # Gán period name cho record
                    metrics["latest_period"] = period_name
                    metrics["bctt_latest_period"] = period_name

                    if args.dry_run:
                        logger.info(f"    [DRY-RUN] Quý {period_name}: {metrics}")
                        records_fetched += 1
                        records_inserted += 1
                    else:
                        status = db_service.save_financial_statement(metrics, stock_id, ds_id)
                        records_fetched += 1
                        if status == "INSERT":
                            records_inserted += 1
                        elif status == "UPDATE":
                            records_updated += 1
                        else:
                            records_failed += 1

                if not args.dry_run and log_id:
                    db_service.write_crawl_log_detail(
                        log_id=log_id,
                        stock_id=stock_id,
                        symbol=symbol,
                        data_type="QUARTERLY_FINANCIAL_STATEMENT",
                        status="SUCCESS",
                        message=f"Thành công cào {len(target_periods)} quý gần nhất: {', '.join(target_periods)}"
                    )

            except Exception as exc:
                elapsed = time.time() - start_time
                err_msg = str(exc)
                logger.error(f"  [{symbol}] ERROR after {elapsed:.1f}s: {err_msg}")
                records_failed += 1
                
                if not args.dry_run and log_id:
                    db_service.write_crawl_log_detail(
                        log_id=log_id,
                        stock_id=stock_id,
                        symbol=symbol,
                        data_type="QUARTERLY_FINANCIAL_STATEMENT",
                        status="FAILED",
                        message=err_msg
                    )

            # Delay giữa các mã tránh bị block
            if idx < total_stocks and args.delay > 0:
                time.sleep(args.delay)

    # Cập nhật kết thúc crawl log
    if not args.dry_run and log_id:
        status_summary = "SUCCESS" if records_failed == 0 else "PARTIAL_SUCCESS"
        if records_fetched == 0 and records_failed > 0:
            status_summary = "FAILED"
        
        db_service.update_crawl_log(
            log_id=log_id,
            ended_at=datetime.utcnow(),
            status=status_summary,
            records_fetched=records_fetched,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed,
            error_message=""
        )
        logger.info(f"\n[MongoDB] Cập nhật xong CrawlLog ID: {log_id} (Trạng thái: {status_summary})")

    logger.info("\n" + "=" * 50)
    logger.info("CRAWL QUARTERLY FINANCIAL STATEMENTS SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Tổng số mã xử lý: {total_stocks}")
    logger.info(f"Số bản ghi quý cào được: {records_fetched}")
    logger.info(f"Thêm mới (Insert DB): {records_inserted}")
    logger.info(f"Cập nhật (Update DB): {records_updated}")
    logger.info(f"Thất bại (Failed): {records_failed}")
    logger.info("=" * 50 + "\n")

if __name__ == "__main__":
    main()
