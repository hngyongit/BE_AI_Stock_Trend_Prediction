import asyncio

from analyse.config.settings import Settings
from analyse.schemas.llm import LLMGenerateResult
from analyse.schemas.report import AnalyseOneReportRequest
from analyse.schemas.research import ExternalResearchContext
from analyse.services.report_service import ReportService
from analyse.services.watchlist_service import WatchlistService


class FakeBackendClient:
    async def get_watchlists(self):
        return {
            "data": {
                "items": [
                    {"stock": {"symbol": "FPT"}},
                    {"stock": {"symbol": "CMG"}},
                    {"stock": {"symbol": "MWG"}},
                    {"stock": {"symbol": "HPG"}},
                    {"stock": {"symbol": "VCB"}},
                    {"stock": {"symbol": "SSI"}},
                ]
            }
        }

    async def get_stock_detail(self, symbol: str):
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

    async def get_stock_chart(self, symbol: str, range_value: str = "1m"):
        return {"data": [{"time": "2026-06-01", "close": 90.0}, {"time": "2026-06-22", "close": 100.0}]}


class FakeResearchService:
    async def search(self, symbol: str, company: str | None = None):
        return ExternalResearchContext(enabled=True, status="success", items=[], flag_summary={})


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


def test_symbol_outside_first_five_watchlist_returns_error():
    settings = Settings(ANALYSE_ONE_SYMBOL_ONLY=True, ENABLE_EXTERNAL_RESEARCH=False)
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "SSI", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request))

    assert result["code"] == 403
    assert result["error"]["type"] == "SYMBOL_NOT_IN_WATCHLIST"


def test_report_service_uses_requested_provider_and_model(monkeypatch):
    captured = {}

    def fake_factory(provider, settings, model=None):
        captured["provider"] = provider
        captured["model"] = model
        return FakeLLMProvider(provider, model or settings.gemini_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(GEMINI_MODEL="gemini-env", ENABLE_EXTERNAL_RESEARCH=False)
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "gemini", "model": "gemini-request", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request))

    assert captured == {"provider": "gemini", "model": "gemini-request"}
    assert result["data"]["provider"]["name"] == "gemini"
    assert result["data"]["provider"]["model"] == "gemini-request"


def test_report_service_falls_back_to_env_model_when_request_model_missing(monkeypatch):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(OPENAI_MODEL="gpt-env", ENABLE_EXTERNAL_RESEARCH=False)
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request))

    assert result["data"]["provider"]["name"] == "openai"
    assert result["data"]["provider"]["model"] == "gpt-env"


def test_llm_output_is_merged_without_overwriting_numeric_fields(monkeypatch):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(OPENAI_MODEL="gpt-env", ENABLE_EXTERNAL_RESEARCH=False)
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request))
    summary = result["data"]["summary"]

    assert summary["latest_market"]["close_price"] == 100.0
    assert summary["scores"]["overall_score"] is None
    assert "LLM ghi nhận nền tảng kinh doanh tích cực." in summary["strengths"]
    assert "LLM bổ sung lý do diễn giải." in summary["system_decision"]["reasons"]
    assert "LLM chỉ thấy dữ liệu BCTC rút gọn." in summary["data_quality_notes"]
    assert result["data"]["markdown_report"]["content"].startswith("# Báo cáo LLM")
    assert "Báo cáo chỉ phục vụ tham khảo/học tập" in result["data"]["markdown_report"]["content"]
