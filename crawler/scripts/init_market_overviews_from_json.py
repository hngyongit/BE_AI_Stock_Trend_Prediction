"""Initialize market_overviews collection from marketoverview.json.

Usage:
    python scripts/init_market_overviews_from_json.py

Requires MONGODB_URI in .env or environment variable.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vietstock_crawler.services.mongodb_service import MongoDBService
from vietstock_crawler.utils.market_overview_utils import normalize_market_overview

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_json_data(json_path: Path) -> list[dict]:
    """Load raw data from JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("data", [])


def init_from_json(json_path: Path, symbol: str = "VNINDEX", source: str = "json_init") -> int:
    """
    Initialize market_overviews collection from JSON file.

    Args:
        json_path: Path to the marketoverview.json file
        symbol: Symbol to assign to all records (default: VNINDEX)
        source: Source identifier for the records

    Returns:
        Number of successfully upserted records
    """
    load_dotenv()

    db_service = MongoDBService()
    if not db_service.is_connected():
        logger.error("Cannot connect to MongoDB. Check MONGODB_URI in .env")
        return 0

    # Ensure indexes
    db_service.ensure_market_overview_indexes()

    raw_records = load_json_data(json_path)
    logger.info(f"Loaded {len(raw_records)} records from {json_path}")

    count = 0
    for i, raw in enumerate(raw_records, start=1):
        logger.info(f"Processing record {i}/{len(raw_records)} ...")

        # Add symbol to the raw record (API payloads don't include it)
        raw_with_symbol = dict(raw)
        raw_with_symbol["symbol"] = symbol

        record = normalize_market_overview(raw_with_symbol, source=source)

        if record is None:
            logger.warning(f"  Record {i}: normalization returned None, skipping.")
            continue

        result = db_service.upsert_market_overview(record)
        logger.info(f"  -> {result}")
        if result in ("INSERT", "UPDATE"):
            count += 1

    return count


def main() -> None:
    json_path = ROOT / "scripts" / "marketoverview.json"
    if not json_path.exists():
        logger.error(f"JSON file not found: {json_path}")
        sys.exit(1)

    count = init_from_json(json_path)
    if count:
        logger.info(f"Done. Initialized {count} market overview records.")
    else:
        logger.warning("No records were initialized.")


if __name__ == "__main__":
    main()