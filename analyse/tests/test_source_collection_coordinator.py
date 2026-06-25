from __future__ import annotations

import asyncio

from analyse.config.settings import Settings
from analyse.services.source_collection_coordinator import SourceCollectionCoordinator
from analyse.services.stock_data_service import StockDataService


class FakeBackendClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def get_stock_analysis_data(
        self,
        symbol: str,
        *,
        token: str,
        exchange: str | None = None,
        quarters: int = 6,
        chart_range: str = "3m",
        include_peers: bool = True,
        include_market_context: bool = True,
    ):
        self.calls.append(("analysis-data", token))
        return {
            "data": {
                "symbol": symbol,
                "exchange": exchange or "HOSE",
                "company": "Cong ty Co phan FPT",
                "latestMarket": {"close_price": 100.0},
                "priceHistory": [{"time": "2026-06-24", "close": 100.0}],
                "financials": {"periods": [{"period": "Q1/2026", "revenue": 1, "profit_after_tax": 1}]},
            }
        }

    async def get_stock_detail(self, symbol: str, *, token: str):
        self.calls.append(("stock-detail", token))
        return {"data": {"symbol": symbol, "latest_price": {"close_price": 99.0}}}

    async def get_stock_chart(self, symbol: str, range_value: str = "1m", *, token: str):
        self.calls.append(("stock-chart", token))
        return {"data": [{"time": "2026-06-24", "close": 99.0}]}


class FakeBackendClientAnalysisDataFails(FakeBackendClient):
    async def get_stock_analysis_data(
        self,
        symbol: str,
        *,
        token: str,
        exchange: str | None = None,
        quarters: int = 6,
        chart_range: str = "3m",
        include_peers: bool = True,
        include_market_context: bool = True,
    ):
        self.calls.append(("analysis-data", token))
        raise RuntimeError("500 Internal Server Error")


class FakeBackendClientOptionalFallbacksFail(FakeBackendClientAnalysisDataFails):
    async def get_stock_detail(self, symbol: str, *, token: str):
        self.calls.append(("stock-detail", token))
        raise RuntimeError("500 Internal Server Error")

    async def get_stock_chart(self, symbol: str, range_value: str = "1m", *, token: str):
        self.calls.append(("stock-chart", token))
        raise RuntimeError("500 Internal Server Error")


def _settings(tmp_path, **overrides):
    return Settings(
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        ENABLE_EXTERNAL_RESEARCH=False,
        **overrides,
    )


def test_collect_backend_stock_sources_uses_analysis_data_and_forwards_token(tmp_path):
    backend = FakeBackendClient()
    coordinator = SourceCollectionCoordinator(
        _settings(tmp_path),
        backend_client=backend,
        stock_data_service=StockDataService(),
    )

    result = asyncio.run(
        coordinator.collect_backend_stock_sources(
            symbol="FPT",
            exchange="HOSE",
            token="request-token",
        )
    )

    assert backend.calls == [("analysis-data", "request-token")]
    assert result.backend_analysis_data is not None
    assert result.normalized_stock_payload is not None
    assert result.normalized_stock_payload["symbol"] == "FPT"
    assert result.normalized_stock_payload["_source_success"]["analysis_data_loaded"] is True
    assert result.normalized_stock_payload["_source_success"]["chart_loaded"] is True
    assert [source.name for source in result.data_source_statuses] == ["Backend /api/stocks/:symbol/analysis-data"]
    assert result.data_source_statuses[0].status == "success"
    assert result.warnings == []


def test_collect_backend_stock_sources_falls_back_to_detail_and_chart(tmp_path):
    backend = FakeBackendClientAnalysisDataFails()
    coordinator = SourceCollectionCoordinator(
        _settings(tmp_path),
        backend_client=backend,
        stock_data_service=StockDataService(),
    )

    result = asyncio.run(
        coordinator.collect_backend_stock_sources(
            symbol="FPT",
            exchange="HOSE",
            token="request-token",
        )
    )

    assert backend.calls == [
        ("analysis-data", "request-token"),
        ("stock-detail", "request-token"),
        ("stock-chart", "request-token"),
    ]
    assert result.backend_analysis_data is None
    assert result.backend_stock_detail is not None
    assert result.backend_stock_chart is not None
    assert result.normalized_stock_payload is not None
    assert result.normalized_stock_payload["_source_success"]["backend_stock_detail_loaded"] is True
    assert result.normalized_stock_payload["_source_success"]["chart_loaded"] is True
    assert any("analysis-data" in warning for warning in result.warnings)
    statuses = {(source.name, source.status) for source in result.data_source_statuses}
    assert ("Backend /api/stocks/:symbol/analysis-data", "failed") in statuses
    assert ("Backend /api/stocks/:symbol", "success") in statuses
    assert ("Backend /api/stocks/:symbol/chart", "success") in statuses


def test_collect_backend_stock_sources_keeps_reportable_payload_when_optional_fallbacks_fail(tmp_path):
    backend = FakeBackendClientOptionalFallbacksFail()
    coordinator = SourceCollectionCoordinator(
        _settings(tmp_path),
        backend_client=backend,
        stock_data_service=StockDataService(),
    )

    result = asyncio.run(
        coordinator.collect_backend_stock_sources(
            symbol="FPT",
            exchange="HOSE",
            token="request-token",
        )
    )

    assert result.normalized_stock_payload is not None
    assert result.normalized_stock_payload["symbol"] == "FPT"
    assert result.normalized_stock_payload["_source_success"]["analysis_data_loaded"] is False
    assert result.normalized_stock_payload["_source_success"]["backend_stock_detail_loaded"] is False
    assert result.normalized_stock_payload["_source_success"]["chart_loaded"] is False
    assert any("/api/stocks/:symbol" in warning for warning in result.warnings)
    statuses = {(source.name, source.status) for source in result.data_source_statuses}
    assert ("Backend /api/stocks/:symbol/analysis-data", "failed") in statuses
    assert ("Backend /api/stocks/:symbol", "failed") in statuses
    assert ("Backend /api/stocks/:symbol/chart", "failed") in statuses
