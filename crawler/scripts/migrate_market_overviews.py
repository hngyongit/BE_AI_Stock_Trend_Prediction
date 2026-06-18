"""Migration script to transfer historical data from market_overviews to factMarketOverviews collection.

Usage:
    python scripts/migrate_market_overviews.py
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

# Setup paths
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run_migration() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")
    load_dotenv(dotenv_path=ROOT.parent / ".env")

    uri = os.getenv("MONGODB_URI")
    if not uri:
        logger.error("MONGODB_URI environment variable not found.")
        return

    logger.info("Connecting to MongoDB...")
    client = MongoClient(uri)
    db = client.get_default_database()

    source_col = db["market_overviews"]
    dest_col = db["factMarketOverviews"]
    markets_col = db["dimMarkets"]

    total_records = source_col.count_documents({})
    logger.info(f"Found {total_records} records in market_overviews to migrate.")

    if total_records == 0:
        logger.info("No records to migrate.")
        return

    # Cache markets by code
    markets_cache = {}
    for m in markets_col.find():
        code = m.get("code", "").upper()
        if code:
            markets_cache[code] = m["_id"]

    # Fallback to create HOSE if not exists
    if "HOSE" not in markets_cache:
        res = markets_col.insert_one({
            "code": "HOSE",
            "name": "Sở Giao dịch Chứng khoán Thành phố Hồ Chí Minh",
            "country": "Vietnam",
            "timezone": "Asia/Ho_Chi_Minh",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        markets_cache["HOSE"] = res.inserted_id
        logger.info(f"Created HOSE market metadata (ID: {res.inserted_id})")

    # Ensure dest collection unique index
    try:
        dest_col.create_index(
            [("market_id", 1), ("time_id", 1), ("symbol", 1)],
            unique=True,
            name="idx_unique_market_time_symbol",
        )
    except Exception as e:
        logger.info(f"Unique index creation skipped or already exists: {e}")

    migrated_count = 0
    updated_count = 0

    for i, doc in enumerate(source_col.find(), start=1):
        trading_date = doc.get("trading_date")
        symbol = doc.get("symbol")

        if not trading_date or not symbol:
            logger.warning(f"Record {i}: missing trading_date or symbol, skipping: {doc}")
            continue

        # Parse trading_date to datetime
        if isinstance(trading_date, str):
            try:
                dt = datetime.strptime(trading_date[:10], "%Y-%m-%d")
            except Exception as e:
                logger.warning(f"Record {i}: failed to parse trading_date string: {trading_date}, error: {e}")
                continue
        elif isinstance(trading_date, datetime):
            dt = trading_date
        else:
            logger.warning(f"Record {i}: unknown trading_date type: {type(trading_date)}, skipping")
            continue

        time_id = int(dt.strftime("%Y%m%d"))

        # Resolve market_id
        market_code = doc.get("market", "HOSE").upper()
        if market_code not in markets_cache:
            # Auto-create market if not exists
            res = markets_col.insert_one({
                "code": market_code,
                "name": f"{market_code} Exchange",
                "country": "Vietnam",
                "timezone": "Asia/Ho_Chi_Minh",
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
            markets_cache[market_code] = res.inserted_id
            logger.info(f"Created market {market_code} metadata (ID: {res.inserted_id})")

        market_id = markets_cache[market_code]

        # Prepare fact document
        fact_doc = {
            "market_id": market_id,
            "time_id": time_id,
            "symbol": symbol,
            "display_symbol": doc.get("display_symbol"),
            "market": market_code,
            "reference_index": doc.get("reference_index"),
            "open_index": doc.get("open_index"),
            "close_index": doc.get("close_index"),
            "high_index": doc.get("high_index"),
            "low_index": doc.get("low_index"),
            "change_value": doc.get("change_value"),
            "change_percent": doc.get("change_percent"),
            "matched_volume": doc.get("matched_volume"),
            "matched_value": doc.get("matched_value"),
            "put_through_volume": doc.get("put_through_volume"),
            "put_through_value": doc.get("put_through_value"),
            "total_volume": doc.get("total_volume"),
            "total_value": doc.get("total_value"),
            "market_cap": doc.get("market_cap"),
            "last_trading_time": doc.get("last_trading_time"),
            "source": doc.get("source") or "migration",
            "raw_data": doc.get("raw_data"),
            "updated_at": datetime.utcnow()
        }

        # Query filter for unique index
        filter_query = {
            "market_id": market_id,
            "time_id": time_id,
            "symbol": symbol
        }

        existing = dest_col.find_one(filter_query)
        if existing:
            # Preserve original created_at
            fact_doc.pop("created_at", None)
            dest_col.update_one(filter_query, {"$set": fact_doc})
            updated_count += 1
        else:
            fact_doc["created_at"] = datetime.utcnow()
            dest_col.insert_one(fact_doc)
            migrated_count += 1

        if i % 50 == 0 or i == total_records:
            logger.info(f"Processed {i}/{total_records} records...")

    logger.info(f"Migration completed! Migrated {migrated_count} new records, updated {updated_count} existing records.")


if __name__ == "__main__":
    run_migration()
