from __future__ import annotations

from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings, get_settings
from analyse.providers.provider_factory import get_llm_provider
from analyse.research.research_service import ExternalResearchService
from analyse.schemas.common import api_error, api_success
from analyse.schemas.report import (
    AnalyseOneReportRequest,
    DataSourceStatus,
    HtmlReport,
    MarkdownReport,
    ProviderMetadata,
    ReportData,
    ReportGenerateResponse,
)
from analyse.schemas.stock import StockAnalysisRequest, StockFetchAnalysisRequest
from analyse.schemas.watchlist import WatchlistAnalysisRequest
from analyse.services.html_service import HtmlService
from analyse.services.markdown_service import MarkdownService
from analyse.services.stock_data_service import StockDataService
from analyse.services.summary_service import SummaryService
from analyse.services.watchlist_service import WatchlistService
from analyse.utils.datetime_utils import now_iso, timestamp_for_filename
from analyse.utils.symbol_utils import normalize_symbol


class ReportService:
    """Orchestrator chính cho các route analyse/report."""

    def __init__(
        self,
        settings: Settings | None = None,
        backend_client: BackendClient | None = None,
        research_service: ExternalResearchService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.backend_client = backend_client or BackendClient(self.settings)
        self.research_service = research_service or ExternalResearchService(self.settings)
        self.watchlist_service = WatchlistService(self.settings)
        self.stock_data_service = StockDataService()
        self.summary_service = SummaryService(self.stock_data_service)
        self.markdown_service = MarkdownService()
        self.html_service = HtmlService(self.settings)

    def build_direct_stock_placeholder(self, payload: StockAnalysisRequest) -> dict:
        symbol = normalize_symbol(payload.symbol)
        stock_detail = payload.data.model_dump(by_alias=True)
        summary = self.summary_service.build_summary(
            symbol=symbol,
            stock_detail=stock_detail,
            scope_exchange="HOSE",
            warnings=["Direct stock route là placeholder cho skeleton."],
        )
        return api_success("Phân tích stock placeholder thành công.", data={"symbol": symbol, "summary": summary})

    def build_watchlist_placeholder(self, payload: WatchlistAnalysisRequest) -> dict:
        data = self.watchlist_service.build_placeholder_result(payload.stocks)
        return api_success("Phân tích watchlist placeholder thành công.", data=data)

    async def fetch_and_analyse_stock_placeholder(self, payload: StockFetchAnalysisRequest) -> dict:
        symbol = normalize_symbol(payload.symbol)
        return api_success(
            "Fetch-and-analyse đã khai báo skeleton; endpoint report chính là /api/ai-reports/analyse-one.",
            data={"symbol": symbol, "backend_mode": payload.fetch_from_backend, "status": "NOT_IMPLEMENTED"},
        )

    async def analyse_one_report(self, payload: AnalyseOneReportRequest) -> dict:
        symbol = normalize_symbol(payload.symbol)
        if not symbol:
            return api_error(
                "Không thể tạo report",
                "VALIDATION_ERROR",
                details=[{"field": "symbol", "message": "symbol là bắt buộc"}],
            )

        warnings: list[str] = []
        data_sources: list[DataSourceStatus] = []

        try:
            watchlist_payload = await self.backend_client.get_watchlists()
            watchlist_symbols = self.watchlist_service.extract_symbols_from_backend_payload(watchlist_payload)
            allowed_symbols = self.watchlist_service.limit_symbols(watchlist_symbols)
            data_sources.append(DataSourceStatus(name="Backend /api/watchlists", type="backend_api", status="success"))
        except Exception as exc:
            allowed_symbols = [symbol]
            warnings.append(f"Chưa gọi được /api/watchlists: {exc}")
            data_sources.append(DataSourceStatus(name="Backend /api/watchlists", type="backend_api", status="failed", detail=str(exc)))

        is_allowed, symbol = self.watchlist_service.validate_symbol_allowed(symbol, allowed_symbols)
        if self.settings.analyse_one_symbol_only and not is_allowed:
            return api_error(
                "Symbol không nằm trong 5 mã watchlist hợp lệ",
                "SYMBOL_NOT_IN_WATCHLIST",
                code=403,
                details=[{"field": "symbol", "message": f"{symbol} không nằm trong danh sách {allowed_symbols}"}],
            )

        try:
            stock_payload = await self.backend_client.get_stock_detail(symbol)
            stock_detail = self.stock_data_service.normalize_stock_detail(stock_payload)
            data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol", type="backend_api", status="success"))
        except Exception as exc:
            stock_detail = {"stock": {"symbol": symbol}, "latest_price": {}, "financials": {}}
            warnings.append(f"Chưa gọi được /api/stocks/:symbol: {exc}")
            data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol", type="backend_api", status="failed", detail=str(exc)))

        company = self.stock_data_service.extract_company(stock_detail)
        research_context = await self.research_service.search(symbol=symbol, company=company)
        data_sources.append(
            DataSourceStatus(
                name="External Research",
                type="vietstock_cafef_google_news",
                status=research_context.status,
                detail=f"items={len(research_context.items)}",
            )
        )

        summary = self.summary_service.build_summary(
            symbol=symbol,
            stock_detail=stock_detail,
            research_context=research_context,
            scope_exchange=payload.scope_exchange,
            warnings=warnings,
        )

        provider = get_llm_provider(payload.provider, self.settings)
        llm_result = await provider.generate_report_json(payload={"symbol": symbol, "summary": summary}, schema={})
        warnings.extend(llm_result.warnings)

        timestamp = timestamp_for_filename(self.settings.analyse_timezone)
        report_id = f"{symbol}_{payload.scope_exchange}_{timestamp}"
        markdown_content = self.markdown_service.build(summary) if payload.options.render_markdown else None
        markdown_report = MarkdownReport(
            available=bool(markdown_content),
            output_path=f"{self.settings.report_output_dir}/{report_id}.md" if markdown_content else None,
            content=markdown_content,
        )
        html_report: HtmlReport = self.html_service.build_metadata(report_id, summary) if payload.options.render_html else HtmlReport()

        report = ReportGenerateResponse(
            data=ReportData(
                report_id=report_id,
                generated_at=now_iso(self.settings.analyse_timezone),
                symbol=symbol,
                company=summary.get("company"),
                scope_exchange=payload.scope_exchange,
                language=payload.options.language,
                summary_schema_version=self.settings.summary_schema_version,
                provider=ProviderMetadata(name=payload.provider, model=llm_result.model, status=llm_result.status, latency_ms=llm_result.latency_ms),
                data_sources=data_sources,
                summary=summary,
                markdown_report=markdown_report,
                html_report=html_report,
                warnings=warnings,
            )
        )
        return report.model_dump()
