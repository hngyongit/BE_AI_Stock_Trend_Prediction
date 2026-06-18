"""
Run Vietstock KQGD market overview (Playwright) once and upsert into MongoDB.

Intended to run at the end of the same daily process as `run.py` (market price crawl).
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Optional

from vietstock_crawler.services.mongodb_service import MongoDBService
from vietstock_crawler.utils.market_overview_utils import normalize_kqgd_playwright_row

logger = logging.getLogger(__name__)


def _load_playwright_crawler_module() -> Any:
    """Load `crawler/scripts/market_overview_crawler.py` (not installed as a package)."""
    # this file: src/vietstock_crawler/jobs/market_overview_daily.py -> parents[3] = crawler/
    crawler_root = Path(__file__).resolve().parents[3]
    path = crawler_root / "market_overview_crawler.py"
    if not path.is_file():
        raise FileNotFoundError(f"market_overview_crawler not found: {path}")
    spec = importlib.util.spec_from_file_location("market_overview_crawler", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_daily_market_overview(db_service: MongoDBService) -> None:
    """
    Crawl one KQGD overview row (latest session) and upsert into `fact_market_overview`.

    No-op if MongoDB is not connected.
    """
    if not db_service.is_connected():
        logger.info("[MarketOverview] MongoDB not connected — skip daily market overview.")
        return

    from datetime import datetime
    from zoneinfo import ZoneInfo
    target_date = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()

    mod = _load_playwright_crawler_module()
    run_crawl = getattr(mod, "run_market_overview_crawl")

    logger.info(f"[MarketOverview] Starting daily KQGD overview crawl for {target_date}…")
    result = run_crawl(target_date=target_date, dry_run=False, force=False)
    logger.info(f"[MarketOverview] Daily crawl completed with result: {result}")
    return result

