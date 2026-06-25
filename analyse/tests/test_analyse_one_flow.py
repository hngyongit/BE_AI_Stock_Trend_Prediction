import asyncio
import json
from pathlib import Path

from analyse.config.settings import Settings
from analyse.schemas.llm import LLMGenerateResult
from analyse.schemas.report import AnalyseOneReportRequest
from analyse.schemas.research import ExternalResearchContext, ResearchItem
from analyse.services.ai_report_history_service import AiReportHistoryUnavailableError
from analyse.services.report_service import ReportService
from analyse.services.watchlist_service import WatchlistService


class FakeBackendClient:
    def __init__(self) -> None:
        self.tokens: list[tuple[str, str]] = []

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
        self.tokens.append(("analysis-data", token))
        return {
            "code": 200,
            "message": "ok",
            "data": {
                "symbol": symbol,
                "exchange": exchange or "HOSE",
                "company": "Cong ty Co phan FPT",
                "latestMarket": {
                    "close_price": 100.0,
                    "volume": 1000,
                    "pe": 10.0,
                    "forward_pe": 9.0,
                    "pb": 2.0,
                    "eps": 5000,
                    "roe": 20.0,
                    "ros": 15.0,
                    "roaa": 5.0,
                    "beta": 0.9,
                    "market_cap": 120000,
                    "foreign_net": 1000,
                },
                "priceHistory": [
                    {"time": "2026-06-01", "close": 90.0, "close_price": 90.0, "volume": 800},
                    {"time": "2026-06-12", "close": 95.0, "close_price": 95.0, "volume": 900},
                    {"time": "2026-06-22", "close": 100.0, "close_price": 100.0, "volume": 1000},
                ],
                "financials": {
                    "periods": [
                        {"period": "Q2/2026", "revenue": 1200, "gross_profit": 400, "operating_profit": 260, "profit_after_tax": 210, "parent_profit": 200, "eps": 1000, "total_assets": 5000, "total_liabilities": 2000, "equity": 3000},
                        {"period": "Q1/2026", "revenue": 1000, "gross_profit": 350, "operating_profit": 240, "profit_after_tax": 180, "parent_profit": 170, "eps": 900, "total_assets": 4800, "total_liabilities": 1900, "equity": 2900},
                        {"period": "Q4/2025", "revenue": 950, "gross_profit": 330, "operating_profit": 210, "profit_after_tax": 160, "parent_profit": 150, "eps": 850, "total_assets": 4600, "total_liabilities": 1850, "equity": 2750},
                    ]
                },
                "financialBalance": {"period": "Q2/2026", "total_assets": 5000, "total_liabilities": 2000, "equity": 3000},
                "hoseMarketContext": {"vnindex": 1300.0, "change_percent": 0.4, "regime": "neutral", "foreign_net": 100},
                "marketGeneralContext": {"exchange": "HOSE", "source": "mongo:test"},
                "industryPeerContext": {
                    "industry": {"sector": "Technology", "industry": "Technology"},
                    "peers": [{"symbol": "CMG", "company": "CMC", "close_price": 50, "pe": 12, "pb": 2, "roe": 15, "market_cap": 30000, "momentum_1m": 5}],
                },
                "sameIndustryRecommendation": {"candidates": [{"symbol": "CMG", "company": "CMC", "roe": 15, "momentum_1m": 5}], "method": "mock"},
                "dataQuality": {
                    "financialsLoaded": True,
                    "financialPeriodsCount": 3,
                    "priceHistoryPoints": 3,
                    "marketContextLoaded": True,
                    "peerContextLoaded": True,
                    "missingFields": [],
                    "warnings": [],
                },
            },
        }

    async def get_watchlists(self, *, token: str):
        self.tokens.append(("watchlists", token))
        return {
            "data": {
                "items": [
                    {"watchlist_id": "watch-fpt", "stock": {"id": "stock-fpt", "symbol": "FPT", "market_code": "HOSE"}},
                    {"stock": {"symbol": "CMG"}},
                    {"stock": {"symbol": "MWG"}},
                    {"stock": {"symbol": "HPG"}},
                    {"stock": {"symbol": "VCB"}},
                    {"stock": {"symbol": "SSI"}},
                ]
            }
        }

    async def get_current_user(self, *, token: str):
        self.tokens.append(("current-user", token))
        return {
            "success": True,
            "data": {
                "id": "mongo-user-1",
                "email": "user@example.com",
                "full_name": "Nguyen Van A",
                "role": "USER",
                "plan": "FREE",
            },
        }

    async def get_stock_detail(self, symbol: str, *, token: str):
        self.tokens.append(("stock-detail", token))
        return {
            "data": {
                "symbol": symbol,
                "company_name": "Cong ty Co phan FPT",
                "market_code": "HOSE",
                "latest_price": {
                    "close_price": 100.0,
                    "volume": 1000,
                    "pe": 10.0,
                    "pb": 2.0,
                    "eps": 5000,
                    "roe": 20.0,
                },
                "financials": {"roe": 20.0},
            }
        }

    async def get_stock_chart(self, symbol: str, range_value: str = "1m", *, token: str):
        self.tokens.append(("stock-chart", token))
        return {"data": [{"time": "2026-06-01", "close": 90.0}, {"time": "2026-06-22", "close": 100.0}]}


class FakeBackendClientWatchlist401(FakeBackendClient):
    async def get_watchlists(self, *, token: str):
        raise RuntimeError("401 Unauthorized")


class FakeBackendClientAllStockApisFail(FakeBackendClient):
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
        raise RuntimeError("500 Internal Server Error")

    async def get_stock_detail(self, symbol: str, *, token: str):
        raise RuntimeError("500 Internal Server Error")

    async def get_stock_chart(self, symbol: str, range_value: str = "1m", *, token: str):
        raise RuntimeError("500 Internal Server Error")


class FakeBackendClientMissingFinancials(FakeBackendClient):
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
        payload = await super().get_stock_analysis_data(
            symbol,
            token=token,
            exchange=exchange,
            quarters=quarters,
            chart_range=chart_range,
            include_peers=include_peers,
            include_market_context=include_market_context,
        )
        payload["data"]["financials"] = {"periods": []}
        payload["data"]["financialBalance"] = {}
        payload["data"]["dataQuality"]["financialsLoaded"] = False
        payload["data"]["dataQuality"]["financialPeriodsCount"] = 0
        payload["data"]["dataQuality"]["missingFields"] = ["financials.periods"]
        return payload


class FakeBackendClientMissingPeers(FakeBackendClient):
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
        payload = await super().get_stock_analysis_data(
            symbol,
            token=token,
            exchange=exchange,
            quarters=quarters,
            chart_range=chart_range,
            include_peers=include_peers,
            include_market_context=include_market_context,
        )
        payload["data"]["industryPeerContext"] = {"industry": {}, "peers": []}
        payload["data"]["sameIndustryRecommendation"] = {}
        payload["data"]["dataQuality"]["peerContextLoaded"] = False
        payload["data"]["dataQuality"]["missingFields"] = ["industryPeerContext.peers"]
        return payload


class FakeVietstockFinancialAdapter:
    async def fetch(self, symbol: str):
        return {
            "source": "Vietstock Finance",
            "source_url": f"https://finance.vietstock.vn/{symbol}/tai-chinh.htm?tab=BCTT",
            "fetched_at": "2026-06-22T09:00:00+07:00",
            "unit": "Tỷ đồng",
            "periods": [
                {
                    "period": "Q1/2026",
                    "year": 2026,
                    "quarter": 1,
                    "revenue": 52901,
                    "gross_profit": 8365,
                    "profit_after_tax": 9056,
                    "parent_profit": 8994,
                    "eps": 2886.77,
                    "total_assets": 259328,
                    "total_liabilities": 119546,
                    "equity": 139782,
                }
            ],
            "warnings": [],
            "status": "success",
        }


class FakeVietstockFinancialEmptyAdapter:
    async def fetch(self, symbol: str):
        return {
            "source": "Vietstock Finance",
            "source_url": f"https://finance.vietstock.vn/{symbol}/tai-chinh.htm?tab=BCTT",
            "periods": [],
            "warnings": ["Vietstock Finance chưa cung cấp đủ kỳ BCTC trong lần chạy này."],
            "technical_warnings": [],
            "status": "insufficient",
        }


class FakeCafeFFinancialCrossCheckAdapter:
    def __init__(self) -> None:
        self.called = False

    async def fetch(self, symbol: str, exchange: str | None = None):
        self.called = True
        return {
            "source": "CafeF tài chính",
            "source_url": f"https://cafef.vn/du-lieu/{(exchange or 'HOSE').lower()}/{symbol.lower()}-tai-chinh.chn",
            "periods": [],
            "warnings": ["CafeF chưa cung cấp đủ kỳ tài chính có thể chuẩn hóa trong lần chạy này."],
            "technical_warnings": [],
            "status": "insufficient",
        }


class FakeCafeFFinancialTimeoutAdapter:
    async def fetch(self, symbol: str, exchange: str | None = None):
        return {
            "source": "CafeF tài chính",
            "source_url": f"https://cafef.vn/du-lieu/{(exchange or 'HOSE').lower()}/{symbol.lower()}-tai-chinh.chn",
            "periods": [],
            "warnings": ["CafeF financial page timed out before usable financial periods were extracted."],
            "technical_warnings": [],
            "status": "insufficient",
        }


class FakeVietstockPeerAdapter:
    async def fetch(self, symbol: str):
        return {
            "source": "Vietstock Finance",
            "source_url": f"https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm",
            "fetched_at": "2026-06-22T09:00:00+07:00",
            "industry": "Cùng ngành theo Vietstock Finance",
            "peers": [
                {
                    "symbol": "CMG",
                    "company": "CMC",
                    "exchange": "HOSE",
                    "price": 50000,
                    "pe": 12.0,
                    "pb": 2.0,
                    "roe": 15.0,
                    "source": "Vietstock Finance",
                    "source_url": f"https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm",
                    "same_industry_reason": "Có trong bảng so sánh cùng ngành Vietstock Finance.",
                    "confidence": 0.75,
                }
            ],
            "warnings": [],
            "status": "success",
        }


class FakeResearchService:
    async def search(self, symbol: str, company: str | None = None):
        return ExternalResearchContext(enabled=True, status="success", items=[], flag_summary={})


class FailIfCalledSourceBackedEnrichmentService:
    async def enrich(self, **kwargs):
        raise AssertionError("source-backed enrichment must not run before watchlist validation passes")


class FakeResearchServiceWithItem:
    async def search(self, symbol: str, company: str | None = None):
        return ExternalResearchContext(
            enabled=True,
            status="success",
            items=[
                ResearchItem(
                    source="CafeF",
                    type="google_news_rss",
                    title=f"{symbol} lợi nhuận tăng và cổ tức mới",
                    url="https://cafef.vn/fpt.html",
                    published_at="2026-06-22T09:00:00+07:00",
                    snippet="Tin public cần kiểm chứng từ nguồn gốc.",
                    tone="tích cực",
                    relevance_score=0.9,
                    positive_flags=["lợi nhuận tăng", "cổ tức"],
                    catalyst_flags=["cổ tức"],
                )
            ],
            flag_summary={"positive_flags": ["lợi nhuận tăng"], "catalyst_flags": ["cổ tức"]},
            source_statuses=[{"name": "CafeF", "status": "success", "items": 1}],
        )


class FakeHistoryService:
    def __init__(self) -> None:
        self.calls = []

    async def save_report_after_analysis(self, *, current_user, payload, report_response, matched_watchlist_item):
        self.calls.append(
            {
                "mongo_user_id": current_user.mongo_user_id,
                "symbol": payload.symbol,
                "watchlist_id": matched_watchlist_item.get("watchlist_id") if isinstance(matched_watchlist_item, dict) else None,
                "stock_id": matched_watchlist_item.get("stock_id") if isinstance(matched_watchlist_item, dict) else None,
            }
        )
        report_response["data"]["history_id"] = "history-123"
        return "history-123"


class FailingHistoryService(FakeHistoryService):
    def __init__(self, secret_db_url: str) -> None:
        super().__init__()
        self.secret_db_url = secret_db_url

    async def save_report_after_analysis(self, *, current_user, payload, report_response, matched_watchlist_item):
        self.calls.append(
            {
                "mongo_user_id": current_user.mongo_user_id,
                "symbol": payload.symbol,
                "watchlist_id": matched_watchlist_item.get("watchlist_id") if isinstance(matched_watchlist_item, dict) else None,
                "stock_id": matched_watchlist_item.get("stock_id") if isinstance(matched_watchlist_item, dict) else None,
            }
        )
        raise AiReportHistoryUnavailableError(f"SQL unavailable for {self.secret_db_url}")


class FailIfCalledHistoryService:
    async def save_report_after_analysis(self, **kwargs):
        raise AssertionError("history service must not be called when history is disabled")


class FakeLLMProvider:
    def __init__(self, provider: str, model: str) -> None:
        self.provider_name = provider
        self.model = model

    async def generate_report_json(self, payload, schema=None):
        return LLMGenerateResult(
            provider=self.provider_name,
            model=self.model,
            status="success",
            latency_ms=12,
            data={
                "strengths": ["LLM ghi nhận nền tảng kinh doanh tích cực."],
                "weaknesses": ["LLM ghi nhận cần theo dõi rủi ro thị trường."],
                "system_decision": {"reasons": ["LLM bổ sung lý do diễn giải."]},
                "markdown_report": {"content": "# Báo cáo LLM\n\nNội dung diễn giải."},
                "data_quality_notes": ["LLM chỉ thấy dữ liệu BCTC rút gọn."],
                "latest_market": {"close_price": 999999},
                "scores": {"overall_score": 100},
            },
        )


class FakeLLMProviderWithUnsupportedNumeric(FakeLLMProvider):
    async def generate_report_json(self, payload, schema=None):
        return LLMGenerateResult(
            provider=self.provider_name,
            model=self.model,
            status="success",
            latency_ms=12,
            data={
                "strengths": ["Giá mục tiêu 125,000 VND có thể tạo upside mạnh."],
                "system_decision": {"reasons": ["Điểm tổng 71/100 là dữ liệu nguồn; target 125000 VND cần kiểm chứng."]},
                "action_plan": {
                    "short_term": [
                        {
                            "action": "Theo dõi vùng giá 125000 VND.",
                            "condition": "Chỉ nâng mức đánh giá nếu giá vượt 125000 VND.",
                            "price_zone": 125000,
                            "price_zone_note": "Vùng 125000 VND do mô hình nêu.",
                            "position_size_note": "Không vượt quá 33% danh mục.",
                            "risk_note": "Dừng lỗ 118000 VND nếu tín hiệu sai.",
                            "source_basis": "LLM inference",
                        }
                    ],
                    "medium_term": [],
                    "watch_points": [],
                    "risk_management": [],
                },
                "checklist": [
                    {"label": "Kiểm tra xu hướng giá", "note": "Đối chiếu thanh khoản và dữ liệu nguồn.", "source_basis": "Dữ liệu hiện có"}
                ],
            },
        )


def test_watchlist_limits_to_five_symbols():
    service = WatchlistService(Settings(MAX_WATCHLIST_SYMBOLS=5))
    symbols = ["FPT", "CMG", "MWG", "HPG", "VCB", "SSI"]
    assert service.limit_symbols(symbols) == ["FPT", "CMG", "MWG", "HPG", "VCB"]


def test_watchlist_normalizes_and_validates_symbol():
    service = WatchlistService(Settings(MAX_WATCHLIST_SYMBOLS=5))
    allowed = service.limit_symbols(["FPT", "CMG"])
    ok, symbol = service.validate_symbol_allowed(" fpt ", allowed)
    assert ok is True
    assert symbol == "FPT"


def test_watchlist_extracts_and_returns_matched_mongo_ids():
    service = WatchlistService(Settings(MAX_WATCHLIST_SYMBOLS=5))
    payload = {
        "data": {
            "items": [
                {"watchlist_id": "watch-1", "stock": {"id": "stock-1", "symbol": "FPT", "market_code": "HOSE"}},
                {"watchlist_id": "watch-2", "stock": {"id": "stock-2", "symbol": "VCB", "market_code": "HOSE"}},
            ]
        }
    }

    items = service.extract_items_from_backend_payload(payload)
    matched = service.find_matching_item(" fpt ", requested_exchange="hose", allowed_items=items)

    assert matched is not None
    assert matched["symbol"] == "FPT"
    assert matched["exchange"] == "HOSE"
    assert matched["watchlist_id"] == "watch-1"
    assert matched["stock_id"] == "stock-1"


def test_symbol_outside_first_five_watchlist_returns_error(tmp_path):
    settings = Settings(ANALYSE_ONE_SYMBOL_ONLY=True, ENABLE_EXTERNAL_RESEARCH=False, REPORT_OUTPUT_DIR=str(tmp_path / "reports"))
    backend_client = FakeBackendClient()
    service = ReportService(settings=settings, backend_client=backend_client, research_service=FakeResearchService())
    service.source_collection_coordinator.source_backed_enrichment_service = FailIfCalledSourceBackedEnrichmentService()
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "SSI", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    assert result["code"] == 403
    assert result["error"]["type"] == "SYMBOL_NOT_IN_WATCHLIST"
    assert ("analysis-data", "request-token") not in backend_client.tokens
    assert ("stock-detail", "request-token") not in backend_client.tokens


def test_report_service_requires_request_token(tmp_path):
    settings = Settings(ENABLE_EXTERNAL_RESEARCH=False, REPORT_OUTPUT_DIR=str(tmp_path / "reports"))
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token=""))

    assert result["code"] == 401
    assert result["error"]["type"] == "AUTH_REQUIRED"


def test_report_service_uses_requested_provider_and_model(monkeypatch, tmp_path):
    captured = {}

    def fake_factory(provider, settings, model=None):
        captured["provider"] = provider
        captured["model"] = model
        return FakeLLMProvider(provider, model or settings.gemini_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(GEMINI_MODEL="gemini-env", ENABLE_EXTERNAL_RESEARCH=False, REPORT_OUTPUT_DIR=str(tmp_path / "reports"))
    backend_client = FakeBackendClient()
    service = ReportService(settings=settings, backend_client=backend_client, research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "gemini", "model": "gemini-request", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    assert captured == {"provider": "gemini", "model": "gemini-request"}
    assert result["data"]["provider"]["name"] == "gemini"
    assert result["data"]["provider"]["model"] == "gemini-request"
    assert ("watchlists", "request-token") in backend_client.tokens
    assert ("analysis-data", "request-token") in backend_client.tokens


def test_analyse_one_saves_history_when_enabled(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        ENABLE_AI_REPORT_HISTORY=True,
        AI_REPORT_DB_URL="mssql+pyodbc://user:password@localhost/db",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_COMPANY_FALLBACK=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_PEER_FALLBACK=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    backend_client = FakeBackendClient()
    history_service = FakeHistoryService()
    service = ReportService(
        settings=settings,
        backend_client=backend_client,
        research_service=FakeResearchService(),
        history_service=history_service,
    )
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    assert result["code"] == 200
    assert result["data"]["history_id"] == "history-123"
    assert ("current-user", "request-token") in backend_client.tokens
    assert history_service.calls == [
        {
            "mongo_user_id": "mongo-user-1",
            "symbol": "FPT",
            "watchlist_id": "watch-fpt",
            "stock_id": "stock-fpt",
        }
    ]


def test_analyse_one_history_save_failure_non_blocking_still_returns_success(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    secret_db_url = "mssql+pyodbc://user:sql-secret@localhost/db"
    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        ENABLE_AI_REPORT_HISTORY=True,
        AI_REPORT_DB_URL=secret_db_url,
        AI_REPORT_HISTORY_SAVE_FAILURE_POLICY="non_blocking",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_COMPANY_FALLBACK=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_PEER_FALLBACK=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    history_service = FailingHistoryService(secret_db_url)
    service = ReportService(
        settings=settings,
        backend_client=FakeBackendClient(),
        research_service=FakeResearchService(),
        history_service=history_service,
    )
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    body_text = json.dumps(result, ensure_ascii=False, default=str)
    assert result["code"] == 200
    assert result["data"]["history_status"] == "failed"
    assert result["data"]["report_status"] == "success_with_warnings"
    assert "history_id" not in result["data"]
    assert result["data"]["warnings"].count("Báo cáo đã phân tích thành công nhưng chưa lưu được lịch sử.") == 1
    assert history_service.calls
    assert "sql-secret" not in body_text
    assert secret_db_url not in body_text


def test_analyse_one_history_save_failure_strict_returns_controlled_failure(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    secret_db_url = "mssql+pyodbc://user:sql-secret@localhost/db"
    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        ENABLE_AI_REPORT_HISTORY=True,
        AI_REPORT_DB_URL=secret_db_url,
        AI_REPORT_HISTORY_SAVE_FAILURE_POLICY="strict",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_COMPANY_FALLBACK=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_PEER_FALLBACK=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(
        settings=settings,
        backend_client=FakeBackendClient(),
        research_service=FakeResearchService(),
        history_service=FailingHistoryService(secret_db_url),
    )
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    body_text = json.dumps(result, ensure_ascii=False, default=str)
    assert result["code"] == 503
    assert result["error"]["type"] == "HISTORY_SAVE_FAILED"
    assert result["data"] is None
    assert "sql-secret" not in body_text
    assert secret_db_url not in body_text


def test_analyse_one_history_disabled_sets_history_status_without_crash(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    backend_client = FakeBackendClient()
    settings = Settings(
        ENABLE_AI_REPORT_HISTORY=False,
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_COMPANY_FALLBACK=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_PEER_FALLBACK=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(
        settings=settings,
        backend_client=backend_client,
        research_service=FakeResearchService(),
        history_service=FailIfCalledHistoryService(),
    )
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    assert result["code"] == 200
    assert result["data"]["history_status"] == "disabled"
    assert result["data"]["report_status"] != "failed"
    assert "history_id" not in result["data"]
    assert ("current-user", "request-token") not in backend_client.tokens


def test_report_service_falls_back_to_env_model_when_request_model_missing(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(OPENAI_MODEL="gpt-env", ENABLE_EXTERNAL_RESEARCH=False, REPORT_OUTPUT_DIR=str(tmp_path / "reports"))
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    assert result["data"]["provider"]["name"] == "openai"
    assert result["data"]["provider"]["model"] == "gpt-env"


def test_llm_output_is_merged_without_overwriting_numeric_fields(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    output_dir = tmp_path / "reports"
    settings = Settings(OPENAI_MODEL="gpt-env", ENABLE_EXTERNAL_RESEARCH=False, REPORT_OUTPUT_DIR=str(output_dir))
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    summary = result["data"]["summary"]

    assert summary["latest_market"]["close_price"] == 100.0
    assert isinstance(summary["scores"]["overall_score"], int)
    assert summary["scores"]["overall_score"] != 100
    assert summary["data_coverage"]["financials_loaded"] is True
    assert summary["bctc_3q"]["has_bctc"] is True
    assert summary["financial_balance"]["total_assets"] == 5000
    assert summary["industry_peer_context"]["peers"][0]["symbol"] == "CMG"
    assert "LLM ghi nhận nền tảng kinh doanh tích cực." in summary["strengths"]
    assert "LLM bổ sung lý do diễn giải." in summary["system_decision"]["reasons"]
    assert "LLM chỉ thấy dữ liệu BCTC rút gọn." in summary["data_quality_notes"]
    markdown_report = result["data"]["markdown_report"]
    html_report = result["data"]["html_report"]
    assert markdown_report["content"].startswith("# Báo cáo phân tích cổ phiếu FPT / HOSE")
    assert "Nội dung diễn giải." in markdown_report["content"]
    assert "Báo cáo này chỉ phục vụ tham khảo/học tập" in markdown_report["content"]
    assert markdown_report["output_path"] is not None
    assert html_report["output_path"] is not None
    assert Path(markdown_report["output_path"]).exists()
    assert Path(html_report["output_path"]).exists()
    assert html_report["content"] is None


def test_analyse_one_suppresses_unsupported_llm_exact_numeric_facts(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProviderWithUnsupportedNumeric(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    output_dir = tmp_path / "reports"
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        REPORT_OUTPUT_DIR=str(output_dir),
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    assert set(result) == {"code", "message", "data"}
    assert result["code"] == 200
    data = result["data"]
    summary = data["summary"]
    serialized_summary = json.dumps(
        {
            "strengths": summary.get("strengths"),
            "action_plan": summary.get("action_plan"),
            "investment_plan": summary.get("investment_plan"),
            "report_presentation": summary.get("report_presentation"),
        },
        ensure_ascii=False,
    )
    assert summary["latest_market"]["close_price"] == 100.0
    assert "Theo dõi" in serialized_summary
    assert "125000" not in serialized_summary
    assert "125,000" not in serialized_summary
    assert "118000" not in serialized_summary
    assert "33%" not in serialized_summary
    assert any("số liệu định lượng do mô hình tạo ra" in warning.lower() for warning in data["warnings"])

    artifact = output_dir / "debug" / "FPT_numeric_fact_validation.json"
    assert artifact.exists()
    debug_text = artifact.read_text(encoding="utf-8")
    assert "125000" not in debug_text
    assert "numeric_fact_validation" not in debug_text or "issue_count" in debug_text


def test_watchlist_401_returns_auth_error(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_COMPANY_FALLBACK=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_PEER_FALLBACK=False,
        BACKEND_WATCHLIST_REQUIRED=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClientWatchlist401(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))

    assert result["code"] == 401
    assert result["error"]["type"] == "AUTH_INVALID"
    assert "token không hợp lệ" in result["message"]


def test_report_service_writes_markdown_and_html_files_with_research(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=True,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=False,
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchServiceWithItem())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    data = result["data"]
    md_path = Path(data["markdown_report"]["output_path"])
    html_path = Path(data["html_report"]["output_path"])

    assert md_path.exists()
    assert html_path.exists()
    markdown = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "# Báo cáo phân tích cổ phiếu FPT / HOSE" in markdown
    assert "## 9. Tin tức và dữ liệu bên ngoài" in markdown
    assert "CafeF" in markdown
    assert "<!doctype html>" in html
    assert '<section id="external-research">' in html
    assert "Báo cáo này chỉ phục vụ tham khảo/học tập" in html
    assert data["html_report"]["content"] is None
    assert any(source["name"] == "Tin tức và nghiên cứu bên ngoài" for source in data["data_sources"])


def test_report_service_writes_both_files_when_render_html_true(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    output_dir = tmp_path / "reports"
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        REPORT_OUTPUT_DIR=str(output_dir),
        REPORT_WRITE_MARKDOWN=True,
        REPORT_WRITE_HTML=True,
        REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=False,
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "openai",
            "model": "gpt-env",
            "symbol": "FPT",
            "scopeExchange": "HOSE",
            "options": {
                "includeExternalResearch": False,
                "renderMarkdown": True,
                "renderHtml": True,
            },
        }
    )

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    data = result["data"]

    assert data["markdown_report"]["available"] is True
    assert data["html_report"]["available"] is True
    assert data["html_report"]["template_name"] == "HtmlService.build"
    assert data["html_report"]["content"] is None
    assert Path(data["markdown_report"]["output_path"]).exists()
    assert Path(data["html_report"]["output_path"]).exists()
    source_names = {source["name"] for source in data["data_sources"]}
    assert "Report Markdown file" not in source_names
    assert "Report HTML file" not in source_names
    assert "File Markdown" not in source_names
    assert "File HTML" not in source_names


def test_report_service_warns_when_html_export_disabled_by_settings(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        REPORT_WRITE_MARKDOWN=True,
        REPORT_WRITE_HTML=False,
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "openai",
            "symbol": "FPT",
            "scopeExchange": "HOSE",
            "options": {
                "includeExternalResearch": False,
                "renderMarkdown": True,
                "renderHtml": True,
            },
        }
    )

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    data = result["data"]

    assert data["markdown_report"]["available"] is True
    assert data["html_report"]["available"] is False
    assert data["html_report"]["output_path"] is None
    assert data["html_report"]["template_name"] is None
    assert any("REPORT_WRITE_HTML=false" in warning for warning in data["warnings"])
    assert all("Report HTML file" != source["name"] for source in data["data_sources"])


def test_report_service_warns_when_render_html_false(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        REPORT_WRITE_HTML=True,
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "openai",
            "symbol": "FPT",
            "scopeExchange": "HOSE",
            "options": {
                "includeExternalResearch": False,
                "renderMarkdown": True,
                "renderHtml": False,
            },
        }
    )

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    data = result["data"]

    assert data["html_report"]["available"] is False
    assert data["html_report"]["output_path"] is None
    assert any("options.renderHtml=false" in warning for warning in data["warnings"])
    assert all("Report HTML file" != source["name"] for source in data["data_sources"])


def test_backend_500_sets_coverage_flags_false_and_report_still_generates(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_COMPANY_FALLBACK=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_PEER_FALLBACK=False,
        BACKEND_WATCHLIST_REQUIRED=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClientAllStockApisFail(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "openai",
            "symbol": "FPT",
            "scopeExchange": "HOSE",
            "options": {
                "includeExternalResearch": False,
                "renderMarkdown": True,
                "renderHtml": True,
            },
        }
    )

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    data = result["data"]
    coverage = data["summary"]["data_coverage"]

    assert result["code"] == 200
    assert coverage["analysis_data_loaded"] is False
    assert coverage["backend_stock_detail_loaded"] is False
    assert coverage["latest_price_loaded"] is False
    assert coverage["financials_loaded"] is False
    assert coverage["price_history_points"] == 0
    assert data["summary"]["latest_market"] == {}
    assert data["summary"]["scores"]["score_confidence"] < 0.6
    assert data["markdown_report"]["available"] is True
    assert data["html_report"]["available"] is True
    assert len(data["warnings"]) == len(set(data["warnings"]))
    assert any(source["name"] == "Dữ liệu giá và thanh khoản" and source["status"] == "failed" for source in data["data_sources"])
    assert any(source["name"] == "Hồ sơ cổ phiếu đã xác thực" and source["status"] == "failed" for source in data["data_sources"])
    assert any(source["name"] == "Chuỗi giá" and source["status"] == "failed" for source in data["data_sources"])


def test_vietstock_financial_fallback_fills_missing_bctc(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=False,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=True,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClientMissingFinancials(), research_service=FakeResearchService())
    service.vietstock_financial_adapter = FakeVietstockFinancialAdapter()
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "openai",
            "symbol": "HPG",
            "scopeExchange": "HOSE",
            "options": {
                "includeExternalResearch": False,
                "renderMarkdown": True,
                "renderHtml": True,
            },
        }
    )

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    data = result["data"]
    summary = data["summary"]

    assert result["code"] == 200
    assert summary["data_coverage"]["financials_loaded"] is True
    assert summary["bctc_3q"]["has_bctc"] is True
    assert summary["bctc_3q"]["periods"][0]["period"] == "Q1/2026"
    assert summary["financial_balance"]["total_assets"] == 259328
    assert any(source["name"] == "Vietstock Finance BCTC" and source["status"] == "success" for source in data["data_sources"])
    assert "Báo cáo đã bổ sung dữ liệu tài chính từ Vietstock Finance" in " ".join(summary["data_quality_notes"])


def test_vietstock_bctc_success_still_attempts_cafef_financial(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=True,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=True,
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClientMissingFinancials(), research_service=FakeResearchService())
    service.vietstock_financial_adapter = FakeVietstockFinancialAdapter()
    cafef_adapter = FakeCafeFFinancialCrossCheckAdapter()
    service.cafef_financial_adapter = cafef_adapter
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "openai",
            "symbol": "HPG",
            "scopeExchange": "HOSE",
            "options": {
                "includeExternalResearch": False,
                "renderMarkdown": False,
                "renderHtml": False,
            },
        }
    )

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    data = result["data"]

    assert result["code"] == 200
    assert cafef_adapter.called is True
    assert any(source["name"] == "Vietstock Finance BCTC" and source["status"] == "success" for source in data["data_sources"])
    assert any(source["name"] == "CafeF tài chính" and source["status"] == "insufficient" for source in data["data_sources"])
    assert not any(source["name"] == "CafeF tài chính" and source["status"] == "skipped" for source in data["data_sources"])


def test_analyse_one_returns_report_when_cafef_financial_times_out(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=True,
        ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=True,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClientMissingFinancials(), research_service=FakeResearchService())
    service.vietstock_financial_adapter = FakeVietstockFinancialEmptyAdapter()
    service.cafef_financial_adapter = FakeCafeFFinancialTimeoutAdapter()
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "openai",
            "symbol": "VCB",
            "scopeExchange": "HOSE",
            "options": {
                "includeExternalResearch": False,
                "renderMarkdown": False,
                "renderHtml": False,
            },
        }
    )

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    serialized_sources = str(result["data"]["data_sources"])

    assert result["code"] == 200
    assert any(source["name"] == "CafeF tài chính" and source["status"] == "failed" for source in result["data"]["data_sources"])
    assert "https://cafef.vn" not in serialized_sources
    assert "periods=0" not in serialized_sources
    attempt_path = tmp_path / "reports" / "debug" / "VCB_cafef_financial_attempt.json"
    assert attempt_path.exists()
    attempt = attempt_path.read_text(encoding="utf-8")
    assert '"attempted": true' in attempt
    assert '"periods_found": 0' in attempt
    assert "request-token" not in attempt
    assert "sk-" not in attempt


def test_vietstock_peer_fallback_fills_missing_peer_context(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_CAFEF_COMPANY_FALLBACK=False,
        ENABLE_VIETSTOCK_PEER_FALLBACK=True,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClientMissingPeers(), research_service=FakeResearchService())
    service.vietstock_peer_adapter = FakeVietstockPeerAdapter()
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "openai",
            "symbol": "FPT",
            "scopeExchange": "HOSE",
            "options": {
                "includeExternalResearch": False,
                "renderMarkdown": True,
                "renderHtml": True,
            },
        }
    )

    result = asyncio.run(service.analyse_one_report(request, user_token="request-token"))
    data = result["data"]
    summary = data["summary"]

    assert result["code"] == 200
    assert summary["data_coverage"]["peer_context_loaded"] is True
    assert summary["industry_peer_context"]["peers"][0]["symbol"] == "CMG"
    assert summary["same_industry_recommendation"]["candidates"][0]["ticker"] == "CMG"
    assert summary["same_industry_recommendation"]["candidates"][0]["confidence"] >= 0.75
    assert any(source["name"] == "Vietstock peer cùng ngành" and source["status"] == "success" for source in data["data_sources"])
    assert "CMG" in data["markdown_report"]["content"]
    assert "Tỷ lệ tin cậy" in data["markdown_report"]["content"]
