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
    path = crawler_root / "scripts" / "market_overview_crawler.py"
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
    Crawl one KQGD overview row (latest session) and upsert into `market_overviews`.

    No-op if MongoDB is not connected.
    """
    if not db_service.is_connected():
        logger.info("[MarketOverview] MongoDB not connected — skip daily market overview.")
        return

    mod = _load_playwright_crawler_module()
    crawl = getattr(mod, "crawl_market_overview")
    fallback = getattr(mod, "crawl_with_manual_post")

    logger.info("[MarketOverview] Starting daily KQGD overview crawl…")
    raw: Optional[dict[str, Any]] = crawl()
    if not raw:
        logger.warning("[MarketOverview] Primary crawl failed, trying manual POST fallback…")
        raw = fallback()

    if not raw:
        logger.error("[MarketOverview] Crawl failed — no data to persist.")
        return

    record = normalize_kqgd_playwright_row(raw)
    if not record:
        logger.error("[MarketOverview] Normalization failed — skip upsert.")
        return

    db_service.ensure_market_overview_indexes()
    outcome = db_service.upsert_market_overview(record)
    logger.info(
        "[MarketOverview] Upsert finished: symbol=%s trading_date=%s outcome=%s",
        record.get("symbol"),
        record.get("trading_date"),
        outcome,
    )
