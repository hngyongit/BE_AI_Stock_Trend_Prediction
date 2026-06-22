from __future__ import annotations

from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings, get_settings
from analyse.providers.provider_factory import get_llm_provider
from analyse.research.research_service import ExternalResearchService
from analyse.schemas.common import ProviderName, api_error, api_success
from analyse.schemas.llm import LLMReportOutput
from analyse.schemas.report import (
    AnalyseOneReportRequest,
    DataSourceStatus,
    HtmlReport,
    MarkdownReport,
    ProviderMetadata,
    ReportData,
    ReportGenerateResponse,
)
from analyse.schemas.research import ExternalResearchContext
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
        provider_name: ProviderName = payload.provider or self.settings.default_llm_provider

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

        if hasattr(self.backend_client, "get_stock_chart"):
            try:
                chart_range = self._chart_range_for_time_horizon(payload.options.time_horizon)
                chart_payload = await self.backend_client.get_stock_chart(symbol, range_value=chart_range)
                stock_detail = self.stock_data_service.merge_chart_history(stock_detail, chart_payload)
                data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol/chart", type="backend_api", status="success", detail=f"range={chart_range}"))
            except Exception as exc:
                warnings.append(f"Chưa gọi được /api/stocks/:symbol/chart: {exc}")
                data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol/chart", type="backend_api", status="partial", detail=str(exc)))

        company = self.stock_data_service.extract_company(stock_detail)
        if payload.options.include_external_research:
            research_context = await self.research_service.search(symbol=symbol, company=company)
            data_sources.append(
                DataSourceStatus(
                    name="External Research",
                    type="vietstock_cafef_google_news",
                    status=research_context.status,
                    detail=f"items={len(research_context.items)}",
                )
            )
        else:
            research_context = ExternalResearchContext(enabled=False, status="disabled", items=[], flag_summary={})
            data_sources.append(DataSourceStatus(name="External Research", type="vietstock_cafef_google_news", status="disabled", detail="request option disabled"))

        summary = self.summary_service.build_summary(
            symbol=symbol,
            stock_detail=stock_detail,
            research_context=research_context,
            scope_exchange=payload.scope_exchange,
            warnings=warnings,
        )
        summary = self._apply_request_risk_defaults(summary, payload)

        selected_model = self._select_model_override(payload.model, warnings)
        provider = get_llm_provider(provider_name, self.settings, model=selected_model)
        llm_result = await provider.generate_report_json(
            payload={
                "symbol": symbol,
                "scope_exchange": payload.scope_exchange,
                "options": payload.options.model_dump(by_alias=True),
                "summary": summary,
            },
            schema=LLMReportOutput.model_json_schema(),
        )
        warnings.extend(llm_result.warnings)
        llm_markdown_content: str | None = None
        if llm_result.status == "success":
            summary, llm_markdown_content = self._merge_llm_output(summary, llm_result.data)

        timestamp = timestamp_for_filename(self.settings.analyse_timezone)
        report_id = f"{symbol}_{payload.scope_exchange}_{timestamp}"
        markdown_content = None
        if payload.options.render_markdown:
            markdown_content = self.markdown_service.finalize_content(llm_markdown_content, summary) or self.markdown_service.build(summary)
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
                provider=ProviderMetadata(name=provider_name, model=llm_result.model, status=llm_result.status, latency_ms=llm_result.latency_ms),
                data_sources=data_sources,
                summary=summary,
                markdown_report=markdown_report,
                html_report=html_report,
                warnings=warnings,
            )
        )
        return report.model_dump()

    def _chart_range_for_time_horizon(self, time_horizon: str) -> str:
        if time_horizon in {"short", "short_term"}:
            return "1m"
        if time_horizon in {"long", "long_term"}:
            return "1y"
        return "3m"

    def _select_model_override(self, requested_model: str | None, warnings: list[str]) -> str | None:
        if not requested_model:
            return None
        if self.settings.allow_request_model_override:
            return requested_model
        warnings.append("Request có model nhưng ALLOW_REQUEST_MODEL_OVERRIDE=false nên dùng model mặc định từ môi trường.")
        return None

    def _apply_request_risk_defaults(self, summary: dict, payload: AnalyseOneReportRequest) -> dict:
        merged = dict(summary)
        plan = dict(merged.get("investment_plan") or {})
        position_sizing = dict(plan.get("position_sizing") or {})
        position_sizing.setdefault("capital_vnd", payload.options.capital_vnd or self.settings.default_capital_vnd)
        position_sizing.setdefault("risk_per_trade_pct", payload.options.risk_per_trade_pct or self.settings.default_risk_per_trade_pct)
        position_sizing.setdefault("max_position_pct", payload.options.max_position_pct or self.settings.default_max_position_pct)
        plan["position_sizing"] = position_sizing
        plan["risk_profile"] = payload.options.risk_profile
        plan["time_horizon"] = payload.options.time_horizon
        merged["investment_plan"] = plan
        return merged

    def _merge_llm_output(self, summary: dict, llm_data: dict) -> tuple[dict, str | None]:
        merged = dict(summary)
        source = llm_data.get("summary") if isinstance(llm_data.get("summary"), dict) else llm_data

        strengths = self._string_list(source.get("strengths"))
        if strengths:
            merged["strengths"] = self._merge_string_lists(merged.get("strengths"), strengths)

        weaknesses = self._string_list(source.get("weaknesses"))
        if weaknesses:
            merged["weaknesses"] = self._merge_string_lists(merged.get("weaknesses"), weaknesses)

        decision = dict(merged.get("system_decision") or {})
        source_decision = source.get("system_decision") if isinstance(source.get("system_decision"), dict) else {}
        reasons = self._string_list(source_decision.get("reasons"))
        if reasons:
            decision["reasons"] = self._merge_string_lists(decision.get("reasons"), reasons)
        merged["system_decision"] = decision

        notes = self._string_list(llm_data.get("data_quality_notes") or source.get("data_quality_notes"))
        if notes:
            merged["data_quality_notes"] = self._merge_string_lists(merged.get("data_quality_notes"), notes)
            bctc_3q = dict(merged.get("bctc_3q") or {})
            bctc_3q["data_quality_notes"] = self._merge_string_lists(bctc_3q.get("data_quality_notes"), notes)
            merged["bctc_3q"] = bctc_3q

        markdown_report = llm_data.get("markdown_report") or source.get("markdown_report")
        markdown_content = None
        if isinstance(markdown_report, dict):
            content = markdown_report.get("content")
            if isinstance(content, str) and content.strip():
                markdown_content = content.strip()

        return merged, markdown_content

    def _string_list(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return []

    def _merge_string_lists(self, existing: object, incoming: list[str]) -> list[str]:
        result = self._string_list(existing)
        seen = set(result)
        for item in incoming:
            if item not in seen:
                result.append(item)
                seen.add(item)
        return result
