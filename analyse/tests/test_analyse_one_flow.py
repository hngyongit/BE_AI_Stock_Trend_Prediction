import asyncio
from pathlib import Path

from analyse.config.settings import Settings
from analyse.schemas.llm import LLMGenerateResult
from analyse.schemas.report import AnalyseOneReportRequest
from analyse.schemas.research import ExternalResearchContext, ResearchItem
from analyse.services.report_service import ReportService
from analyse.services.watchlist_service import WatchlistService


class FakeBackendClient:
    async def get_stock_analysis_data(
        self,
        symbol: str,
        exchange: str | None = None,
        quarters: int = 6,
        chart_range: str = "3m",
        include_peers: bool = True,
        include_market_context: bool = True,
    ):
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


class FakeBackendClientWatchlist401(FakeBackendClient):
    async def get_watchlists(self):
        raise RuntimeError("401 Unauthorized")


class FakeResearchService:
    async def search(self, symbol: str, company: str | None = None):
        return ExternalResearchContext(enabled=True, status="success", items=[], flag_summary={})


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


def test_symbol_outside_first_five_watchlist_returns_error(tmp_path):
    settings = Settings(ANALYSE_ONE_SYMBOL_ONLY=True, ENABLE_EXTERNAL_RESEARCH=False, REPORT_OUTPUT_DIR=str(tmp_path / "reports"))
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "SSI", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request))

    assert result["code"] == 403
    assert result["error"]["type"] == "SYMBOL_NOT_IN_WATCHLIST"


def test_report_service_uses_requested_provider_and_model(monkeypatch, tmp_path):
    captured = {}

    def fake_factory(provider, settings, model=None):
        captured["provider"] = provider
        captured["model"] = model
        return FakeLLMProvider(provider, model or settings.gemini_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(GEMINI_MODEL="gemini-env", ENABLE_EXTERNAL_RESEARCH=False, REPORT_OUTPUT_DIR=str(tmp_path / "reports"))
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "gemini", "model": "gemini-request", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request))

    assert captured == {"provider": "gemini", "model": "gemini-request"}
    assert result["data"]["provider"]["name"] == "gemini"
    assert result["data"]["provider"]["model"] == "gemini-request"


def test_report_service_falls_back_to_env_model_when_request_model_missing(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(OPENAI_MODEL="gpt-env", ENABLE_EXTERNAL_RESEARCH=False, REPORT_OUTPUT_DIR=str(tmp_path / "reports"))
    service = ReportService(settings=settings, backend_client=FakeBackendClient(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request))

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

    result = asyncio.run(service.analyse_one_report(request))
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
    assert markdown_report["content"].startswith("# Báo cáo phân tích cổ phiếu FPT trên HOSE")
    assert "Nội dung diễn giải." in markdown_report["content"]
    assert "Báo cáo này chỉ phục vụ tham khảo/học tập" in markdown_report["content"]
    assert markdown_report["output_path"] is not None
    assert html_report["output_path"] is not None
    assert Path(markdown_report["output_path"]).exists()
    assert Path(html_report["output_path"]).exists()
    assert html_report["content"] is None


def test_watchlist_401_does_not_block_when_not_required(monkeypatch, tmp_path):
    def fake_factory(provider, settings, model=None):
        return FakeLLMProvider(provider, model or settings.openai_model)

    monkeypatch.setattr("analyse.services.report_service.get_llm_provider", fake_factory)
    settings = Settings(
        OPENAI_MODEL="gpt-env",
        ENABLE_EXTERNAL_RESEARCH=False,
        BACKEND_WATCHLIST_REQUIRED=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )
    service = ReportService(settings=settings, backend_client=FakeBackendClientWatchlist401(), research_service=FakeResearchService())
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    result = asyncio.run(service.analyse_one_report(request))

    assert result["code"] == 200
    assert result["data"]["summary"]["data_coverage"]["financials_loaded"] is True
    assert any("Không gọi được watchlists do thiếu/sai token" in warning for warning in result["data"]["warnings"])
    assert any(source["name"] == "Backend /api/stocks/:symbol/analysis-data" and source["status"] == "success" for source in result["data"]["data_sources"])


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

    result = asyncio.run(service.analyse_one_report(request))
    data = result["data"]
    md_path = Path(data["markdown_report"]["output_path"])
    html_path = Path(data["html_report"]["output_path"])

    assert md_path.exists()
    assert html_path.exists()
    markdown = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "# Báo cáo phân tích cổ phiếu FPT trên HOSE" in markdown
    assert "## 1C. Nghiên cứu tin tức/ngành/thị trường bên ngoài" in markdown
    assert "CafeF" in markdown
    assert "<!doctype html>" in html
    assert '<section id="external-research">' in html
    assert "Báo cáo này chỉ phục vụ tham khảo/học tập" in html
    assert data["html_report"]["content"] is None
    assert any(source["name"] == "External Research" for source in data["data_sources"])


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

    result = asyncio.run(service.analyse_one_report(request))
    data = result["data"]

    assert data["markdown_report"]["available"] is True
    assert data["html_report"]["available"] is True
    assert data["html_report"]["template_name"] == "HtmlService.build"
    assert data["html_report"]["content"] is None
    assert Path(data["markdown_report"]["output_path"]).exists()
    assert Path(data["html_report"]["output_path"]).exists()
    assert any(source["name"] == "Report Markdown file" and source["status"] == "success" for source in data["data_sources"])
    assert any(source["name"] == "Report HTML file" and source["status"] == "success" for source in data["data_sources"])


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

    result = asyncio.run(service.analyse_one_report(request))
    data = result["data"]

    assert data["markdown_report"]["available"] is True
    assert data["html_report"]["available"] is False
    assert data["html_report"]["output_path"] is None
    assert data["html_report"]["template_name"] is None
    assert any("REPORT_WRITE_HTML=false" in warning for warning in data["warnings"])
    assert any(source["name"] == "Report HTML file" and source["status"] == "disabled" for source in data["data_sources"])


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

    result = asyncio.run(service.analyse_one_report(request))
    data = result["data"]

    assert data["html_report"]["available"] is False
    assert data["html_report"]["output_path"] is None
    assert any("options.renderHtml=false" in warning for warning in data["warnings"])
    assert any(source["name"] == "Report HTML file" and source["status"] == "disabled" for source in data["data_sources"])
