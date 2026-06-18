"""
Playwright crawler for Vietstock daily market overview.
Captures network requests to fetch stock market data and saves to fact_market_overview.
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

# Setup path to import vietstock_crawler
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vietstock_crawler.config.settings import get_settings
from vietstock_crawler.services.mongodb_service import MongoDBService
from vietstock_crawler.utils.date_utils import now_vn_dt

# Fix Unicode/emoji issues for Windows terminal output
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Configure logging
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger(__name__)

# Constants
TARGET_PAGE_URL = "https://finance.vietstock.vn/ket-qua-giao-dich?tab=thong-ke-gia&exchange=1&code=-19"
API_ENDPOINT = "/data/KQGDThongKeGiaStockPaging"
API_BASE_URL = "https://finance.vietstock.vn"


def parse_vietstock_date(value: str) -> str:
    """
    Parse Vietstock ASP.NET date format like '/Date(1781110800000)/'
    Returns ISO date string (YYYY-MM-DD) in Vietnam timezone.
    """
    if not value:
        return ""

    match = re.search(r"\d+", str(value))
    if not match:
        raise ValueError(f"Invalid Vietstock date: {value}")

    timestamp_ms = int(match.group(0))

    dt = datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=timezone.utc
    ).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))

    return dt.date().isoformat()


def normalize_row(row: Dict[str, Any], summary_data: List[Any], source_url: str) -> Dict[str, Any]:
    """
    Normalize a single market overview row into a clean object.
    """
    trading_date = parse_vietstock_date(row.get("TradingDate", ""))
    
    # Extract change_text and transaction_number from summary_data if available
    change_text = ""
    transaction_number = 0
    if summary_data and len(summary_data) > 0:
        first_item = summary_data[0]
        if isinstance(first_item, dict):
            change_text = first_item.get("ChangeText", "")
            transaction_number = first_item.get("TranNo", 0)
    
    return {
        "trading_date": trading_date,
        "stock_code": row.get("StockCode", ""),
        "stock_name": row.get("StockName", ""),
        "reference_price": row.get("BasicPrice"),
        "open_price": row.get("OpenPrice"),
        "close_price": row.get("ClosePrice"),
        "highest_price": row.get("HighestPrice"),
        "lowest_price": row.get("LowestPrice"),
        "price_change": row.get("Change"),
        "price_change_percent": row.get("PerChange"),
        "matched_volume": row.get("M_TotalVol"),
        "matched_value": row.get("M_TotalVal"),
        "put_through_volume": row.get("PT_TotalVol"),
        "put_through_value": row.get("PT_TotalVal"),
        "total_volume": row.get("TotalVol"),
        "total_value": row.get("TotalVal"),
        "market_cap": row.get("MarketCap"),
        "change_color": row.get("ChangeColor", ""),
        "change_text": change_text,
        "transaction_number": transaction_number,
        "source": "vietstock",
        "source_url": source_url,
        "crawled_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }


def crawl_market_overview(target_date: str) -> Optional[Dict[str, Any]]:
    """
    Main crawler function that:
    1. Launches Playwright browser
    2. Opens the target page
    3. Captures the API request
    4. Searches for the row matching target_date
    5. Returns normalized market overview data for target_date
    """
    json_data = None
    captured_request_body = None
    api_response_received = False
    
    with sync_playwright() as p:
        logger.info("Launching Playwright browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1000},
            locale="vi-VN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        )
        
        # Set up request listener BEFORE page creation
        def handle_request(request):
            nonlocal captured_request_body
            if API_ENDPOINT in request.url:
                logger.info(f"API request captured: {request.url}")
                captured_request_body = request.post_data
        
        def handle_response(response):
            nonlocal json_data, api_response_received
            if API_ENDPOINT in response.url:
                logger.info(f"API response received: {response.status}")
                api_response_received = True
                try:
                    json_data = response.json()
                except Exception as e:
                    logger.error(f"Failed to parse response JSON: {e}")
        
        # Create page and set up listeners
        page = context.new_page()
        page.on("request", handle_request)
        page.on("response", handle_response)
        
        logger.info(f"Opening target page: {TARGET_PAGE_URL}")
        page.goto(TARGET_PAGE_URL, wait_until="load", timeout=60000)
        
        # Wait for API response to be received
        logger.info("Waiting for API response...")
        for _ in range(20):  # Wait up to 20 seconds
            if api_response_received:
                break
            page.wait_for_timeout(1000)
        
        browser.close()
    
    # Process captured response
    if not json_data:
        logger.warning("No API response captured automatically.")
        return None
    
    if not isinstance(json_data, list) or len(json_data) < 2:
        logger.error(f"Unexpected response structure. Expected array with at least 2 elements, got: {type(json_data)}")
        return None
    
    summary_data = json_data[0] if len(json_data) > 0 else []
    rows = json_data[1] if len(json_data) > 1 else []
    
    if not rows:
        logger.error("response[1] is missing or empty")
        return None
    
    # Find matching row for target_date
    matching_row = None
    for row in rows:
        try:
            trading_date = parse_vietstock_date(row.get("TradingDate", ""))
            if trading_date == target_date:
                matching_row = row
                break
        except Exception:
            continue
            
    if not matching_row:
        logger.info(f"Target date {target_date} not found in the automatically captured response.")
        return None
        
    logger.info(f"Found matching row for target date {target_date}")
    normalized = normalize_row(matching_row, summary_data, TARGET_PAGE_URL)
    return normalized


def crawl_with_manual_post(target_date: str) -> Optional[Dict[str, Any]]:
    """
    Fallback method: manually POST to the API with target_date filter and a fresh anti-forgery token.
    """
    with sync_playwright() as p:
        logger.info("Launching browser for manual POST fallback...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1000},
            locale="vi-VN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        )
        
        page = context.new_page()
        logger.info(f"Navigating to target page: {TARGET_PAGE_URL}")
        page.goto(TARGET_PAGE_URL, wait_until="load", timeout=60000)
        
        # Extract anti-forgery token
        token = page.eval_on_selector(
            'input[name="__RequestVerificationToken"]',
            'el => el ? el.value : null'
        )
        
        if not token:
            logger.warning("Anti-forgery token not found.")
            browser.close()
            return None
        
        logger.info(f"Anti-forgery token obtained.")
        
        # Prepare POST data with date filters
        post_data = {
            "page": 1,
            "pageSize": 20,
            "catID": 1,
            "stockID": -19,
            "fromDate": target_date,
            "toDate": target_date,
            "__RequestVerificationToken": token
        }
        
        # Make manual POST request using fetch API
        api_url = f"{API_BASE_URL}{API_ENDPOINT}"
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": API_BASE_URL,
            "Referer": TARGET_PAGE_URL,
            "X-Requested-With": "XMLHttpRequest"
        }
        
        logger.info(f"Making manual POST to: {api_url} for date: {target_date}")
        
        try:
            response_data = page.evaluate(
                '''async ({ url, data, headers }) => {
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: headers,
                        body: new URLSearchParams(data).toString()
                    });
                    return await response.json();
                }''',
                {"url": api_url, "data": post_data, "headers": headers}
            )
        except Exception as e:
            logger.error(f"Manual POST fetch request failed: {e}")
            browser.close()
            return None
            
        browser.close()
        
        json_data = response_data
        
        if not isinstance(json_data, list) or len(json_data) < 2:
            logger.error("Unexpected manual POST response structure")
            return None
        
        summary_data = json_data[0] if len(json_data) > 0 else []
        rows = json_data[1] if len(json_data) > 1 else []
        
        if not rows:
            logger.error(f"No rows returned for date: {target_date}")
            return None
            
        # Find matching row for target_date
        matching_row = None
        for row in rows:
            try:
                trading_date = parse_vietstock_date(row.get("TradingDate", ""))
                if trading_date == target_date:
                    matching_row = row
                    break
            except Exception:
                continue
                
        if not matching_row:
            logger.error(f"Target date {target_date} not found in manual POST response rows.")
            return None
            
        normalized = normalize_row(matching_row, summary_data, TARGET_PAGE_URL)
        return normalized


def ensure_dim_time(db, target_date: date) -> int:
    """Ensure dimTimes collection contains the date. Returns time_id."""
    col = db["dimTimes"]
    time_id = int(target_date.strftime("%Y%m%d"))
    existing = col.find_one({"time_id": time_id})
    if existing:
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
        "created_at": datetime.utcnow(),
    }
    try:
        col.insert_one(doc)
        logger.info(f"Created new dimTime: {time_id}")
    except Exception as e:
        logger.warning(f"Failed to create dimTime: {e}")
    return time_id


def run_market_overview_crawl(
    target_date: str,
    dry_run: bool = False,
    force: bool = False,
    crawl_job_id: str | None = None
) -> dict:
    """
    Main standardized crawler interface for manual crawls and daily worker calls.
    """
    logger.info("=" * 60)
    logger.info(f"Starting Market Overview Crawler for date: {target_date}")
    logger.info(f"Parameters: dry_run={dry_run}, force={force}")
    logger.info("=" * 60)

    # 1. Initialize MongoDB service
    db_service = MongoDBService()
    if not db_service.is_connected():
        msg = "MongoDB not connected. Cannot perform database queries/upserts."
        logger.error(msg)
        if not dry_run:
            return {
                "status": "FAILED",
                "date": target_date,
                "records_fetched": 0,
                "records_inserted": 0,
                "records_updated": 0,
                "records_skipped": 0,
                "records_failed": 1,
                "message": msg
            }

    db = db_service.db
    market_id = None
    data_source_id = None
    
    if db_service.is_connected():
        # Get market HOSE
        hose_market = db["dimMarkets"].find_one({"code": {"$in": ["HOSE", "hose"]}})
        if hose_market:
            market_id = hose_market["_id"]
        else:
            # Create HOSE market metadata if missing
            res = db["dimMarkets"].insert_one({
                "code": "HOSE",
                "name": "Sở Giao dịch Chứng khoán Thành phố Hồ Chí Minh",
                "country": "Vietnam",
                "timezone": "Asia/Ho_Chi_Minh",
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
            market_id = res.inserted_id
            logger.info(f"HOSE market created with ID: {market_id}")

        data_source_id = db_service.get_data_source_id("vietstock")

    # Parse target_date to date object and time_id
    try:
        dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
        time_id = int(dt_obj.strftime("%Y%m%d"))
    except ValueError:
        msg = f"Invalid date format: {target_date}. Expected YYYY-MM-DD."
        logger.error(msg)
        return {
            "status": "FAILED",
            "date": target_date,
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "records_skipped": 0,
            "records_failed": 1,
            "message": msg
        }

    # Ensure dimTimes exists
    if db_service.is_connected() and not dry_run:
        ensure_dim_time(db, dt_obj.date())

    # Check for existing record
    collection_name = "factMarketOverviews"
    if db_service.is_connected() and not dry_run:
        db_service.ensure_market_overview_indexes()
        
        query = {
            "market_id": market_id,
            "time_id": time_id
        }
        existing = db[collection_name].find_one(query)
        if existing:
            if not force:
                msg = f"Market overview data already exists for {target_date}."
                logger.info(f"[SKIP] {msg}")
                return {
                    "status": "SKIPPED",
                    "date": target_date,
                    "records_fetched": 0,
                    "records_inserted": 0,
                    "records_updated": 0,
                    "records_skipped": 1,
                    "records_failed": 0,
                    "message": msg
                }
            else:
                logger.info(f"Force mode enabled. Overwriting existing record for {target_date}.")

    # 2. Crawl
    crawled_data = crawl_market_overview(target_date)
    if not crawled_data:
        logger.warning("Automatic capture did not find matching date. Trying manual POST fallback...")
        crawled_data = crawl_with_manual_post(target_date)

    if not crawled_data:
        msg = f"Failed to crawl market overview data for {target_date}."
        logger.error(msg)
        return {
            "status": "FAILED",
            "date": target_date,
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "records_skipped": 0,
            "records_failed": 1,
            "message": msg
        }

    # 3. Map data schema
    from vietstock_crawler.utils.market_overview_utils import normalize_kqgd_playwright_row
    overview_doc = normalize_kqgd_playwright_row(crawled_data)
    if not overview_doc:
        msg = f"Failed to normalize crawled market overview row for {target_date}."
        logger.error(msg)
        return {
            "status": "FAILED",
            "date": target_date,
            "records_fetched": 1,
            "records_inserted": 0,
            "records_updated": 0,
            "records_skipped": 0,
            "records_failed": 1,
            "message": msg
        }

    overview_doc["market_id"] = market_id
    overview_doc["time_id"] = time_id

    if dry_run:
        logger.info(f"🔍 [DRY RUN] target_date={target_date} mapped data: {overview_doc}")
        return {
            "status": "SUCCESS",
            "date": target_date,
            "records_fetched": 1,
            "records_inserted": 1,
            "records_updated": 0,
            "records_skipped": 0,
            "records_failed": 0,
            "message": "Market overview dry-run succeeded."
        }

    # 4. Upsert
    try:
        res = db_service.upsert_market_overview(overview_doc)
        logger.info(f"✅ [{res}] Saved market overview for {target_date} into factMarketOverviews")

        records_inserted = 1 if res == "INSERT" else 0
        records_updated = 1 if res == "UPDATE" else 0

        return {
            "status": "SUCCESS",
            "date": target_date,
            "records_fetched": 1,
            "records_inserted": records_inserted,
            "records_updated": records_updated,
            "records_skipped": 0,
            "records_failed": 0,
            "message": f"Market overview crawled and saved successfully: {res}"
        }
    except Exception as e:
        msg = f"Failed to save market overview to MongoDB: {e}"
        logger.error(msg)
        return {
            "status": "FAILED",
            "date": target_date,
            "records_fetched": 1,
            "records_inserted": 0,
            "records_updated": 0,
            "records_skipped": 0,
            "records_failed": 1,
            "message": msg
        }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Vietstock Market Overview Crawler")
    parser.add_argument(
        "--date",
        help="Target date for the crawl in YYYY-MM-DD format (default: today's date in Vietnam)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Crawl and output data without writing to MongoDB",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing record in MongoDB for this date",
    )
    args = parser.parse_args()

    # Resolve date
    if args.date:
        target_date = args.date
    else:
        target_date = now_vn_dt().date().isoformat()

    result = run_market_overview_crawl(
        target_date=target_date,
        dry_run=args.dry_run,
        force=args.force
    )

    if result["status"] == "SUCCESS":
        return 0
    elif result["status"] == "SKIPPED":
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
