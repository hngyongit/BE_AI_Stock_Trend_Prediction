"""
Playwright crawler for Vietstock daily market overview.
Captures network requests to fetch stock market data.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
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


def get_latest_row(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Get the most recent row by TradingDate.
    """
    if not rows:
        return None
    
    # Parse dates and sort descending
    rows_with_dates = []
    for row in rows:
        trading_date = row.get("TradingDate", "")
        match = re.search(r"/Date\((\d+)\)/", str(trading_date))
        if match:
            timestamp = int(match.group(1))
            rows_with_dates.append((timestamp, row))
    
    if not rows_with_dates:
        return rows[0]  # Fallback to first row
    
    # Sort by timestamp descending and return the latest
    rows_with_dates.sort(key=lambda x: x[0], reverse=True)
    return rows_with_dates[0][1]


def crawl_market_overview() -> Optional[Dict[str, Any]]:
    """
    Main crawler function that:
    1. Launches Playwright browser
    2. Opens the target page
    3. Captures the API request
    4. Returns normalized market overview data
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
                logger.info(f"Request body: {captured_request_body}")
        
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
        # Use 'load' instead of 'networkidle' for faster navigation
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
        logger.warning("No API response captured automatically. Will check if page already sent request.")
        return None
    
    if not isinstance(json_data, list) or len(json_data) < 2:
        logger.error(f"Unexpected response structure. Expected array with at least 2 elements, got: {type(json_data)}")
        return None
    
    summary_data = json_data[0] if len(json_data) > 0 else []
    rows = json_data[1] if len(json_data) > 1 else []
    total_count = json_data[2] if len(json_data) > 2 else 0
    
    logger.info(f"Total rows returned: {total_count}")
    logger.info(f"Rows in response[1]: {len(rows)}")
    
    if not rows:
        logger.error("response[1] is missing or empty")
        return None
    
    # Get the latest row
    latest_row = get_latest_row(rows)
    if not latest_row:
        logger.error("Could not determine latest row")
        return None
    
    logger.info(f"Latest row TradingDate: {latest_row.get('TradingDate')}")
    
    # Normalize the data
    normalized = normalize_row(latest_row, summary_data, TARGET_PAGE_URL)
    
    # Print raw latest row for debugging
    logger.info(f"Raw latest row: {latest_row}")
    
    return normalized


def crawl_with_manual_post() -> Optional[Dict[str, Any]]:
    """
    Fallback method: manually POST to the API with a fresh anti-forgery token.
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
            logger.warning("Anti-forgery token not found. Checking for hidden inputs...")
            hidden_inputs = page.eval_on_selector_all(
                'input[type="hidden"]',
                'els => els.map(el => ({name: el.name, value: el.value}))'
            )
            logger.info(f"Hidden inputs found: {hidden_inputs}")
            browser.close()
            return None
        
        logger.info(f"Anti-forgery token: {token}")
        
        # Prepare POST data
        post_data = {
            "keyword": "",
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
        
        logger.info(f"Making manual POST to: {api_url}")
        
        # Use page.evaluate to make the fetch request
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
        
        browser.close()
        
        json_data = response_data
        
        if not isinstance(json_data, list) or len(json_data) < 2:
            logger.error(f"Unexpected response structure")
            return None
        
        summary_data = json_data[0] if len(json_data) > 0 else []
        rows = json_data[1] if len(json_data) > 1 else []
        
        if not rows:
            logger.error("No rows in response")
            return None
        
        latest_row = get_latest_row(rows)
        if not latest_row:
            return None
        
        normalized = normalize_row(latest_row, summary_data, TARGET_PAGE_URL)
        logger.info(f"Raw latest row: {latest_row}")
        
        return normalized


def main():
    """
    Main entry point for the crawler.
    """
    logger.info("=" * 60)
    logger.info("Starting Vietstock Market Overview Crawler")
    logger.info("=" * 60)
    
    result = crawl_market_overview()
    
    if not result:
        logger.warning("Automatic capture failed. Trying manual POST fallback...")
        result = crawl_with_manual_post()
    
    if result:
        logger.info("=" * 60)
        logger.info("Crawled Data:")
        logger.info("=" * 60)
        # Print parsed trading date
        print(f"\nParsed trading date: {result.get('trading_date')}")
        print(f"\nNormalized Result:")
        print(result)
    else:
        logger.error("Failed to crawl market overview data")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())