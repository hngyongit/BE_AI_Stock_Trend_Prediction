import time
import pytest
import concurrent.futures
from unittest.mock import MagicMock, patch
from bson import ObjectId

from manual_crawl_by_date_improved import crawl_symbol_with_timeout, crawl_single_symbol

def test_crawl_symbol_success():
    # Mock crawl_single_symbol to succeed immediately
    with patch("manual_crawl_by_date_improved.crawl_single_symbol") as mock_crawl:
        mock_crawl.return_value = {"status": "SUCCESS"}
        
        result = crawl_symbol_with_timeout(
            db=MagicMock(),
            stock={"_id": ObjectId(), "symbol": "AAA"},
            target_date=MagicMock(),
            provider_names=["vietstock"],
            data_source_id=ObjectId(),
            time_id=20260605,
            hose_market_id=ObjectId(),
            is_dry_run=True,
            crawl_log_id=ObjectId(),
            timeout=5.0
        )
        assert result["status"] == "SUCCESS"
        mock_crawl.assert_called_once()

def test_crawl_symbol_timeout():
    # Mock crawl_single_symbol to sleep longer than the timeout
    def slow_crawl(*args, **kwargs):
        time.sleep(2.0)
        return {"status": "SUCCESS"}

    with patch("manual_crawl_by_date_improved.crawl_single_symbol", side_effect=slow_crawl):
        with pytest.raises(TimeoutError, match="Timeout > 0.2s"):
            crawl_symbol_with_timeout(
                db=MagicMock(),
                stock={"_id": ObjectId(), "symbol": "AAA"},
                target_date=MagicMock(),
                provider_names=["vietstock"],
                data_source_id=ObjectId(),
                time_id=20260605,
                hose_market_id=ObjectId(),
                is_dry_run=True,
                crawl_log_id=ObjectId(),
                timeout=0.2  # very short timeout
            )
