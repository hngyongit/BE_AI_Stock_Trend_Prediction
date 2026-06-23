from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings, get_settings
from analyse.providers.provider_factory import get_llm_provider
from analyse.research.cafef_company_adapter import CafeFCompanyAdapter
from analyse.research.cafef_financial_adapter import CafeFFinancialAdapter
from analyse.research.research_service import ExternalResearchService
from analyse.research.vietstock_financial_adapter import VietstockFinancialAdapter
from analyse.research.vietstock_peer_adapter import VietstockPeerAdapter
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
from analyse.services.config_diagnostic_service import ConfigDiagnosticService
from analyse.services.markdown_service import MarkdownService
from analyse.services.presentation_contract import build_data_source_debug_rows
from analyse.services.presentation_contract import sanitize_data_source_statuses
from analyse.services.report_file_service import ReportFileService
from analyse.services.stock_data_service import StockDataService
from analyse.services.summary_service import SummaryService
from analyse.services.watchlist_service import WatchlistService
from analyse.utils.datetime_utils import now_iso, timestamp_for_filename
from analyse.utils.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)


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
        self.cafef_company_adapter = CafeFCompanyAdapter(self.settings)
        self.cafef_financial_adapter = CafeFFinancialAdapter(self.settings)
        self.vietstock_financial_adapter = VietstockFinancialAdapter(self.settings)
        self.vietstock_peer_adapter = VietstockPeerAdapter(self.settings)
        self.watchlist_service = WatchlistService(self.settings)
        self.stock_data_service = StockDataService()
        self.summary_service = SummaryService(self.stock_data_service, settings=self.settings)
        self.markdown_service = MarkdownService()
        self.html_service = HtmlService(self.settings)
        self.report_file_service = ReportFileService(self.settings.report_output_dir)

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

    async def analyse_one_report(self, payload: AnalyseOneReportRequest, *, user_token: str | None = None) -> dict:
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
        if not str(user_token or "").strip():
            return api_error(
                "Missing Authorization header. Please login again.",
                "AUTH_REQUIRED",
                code=401,
                details=[{"field": "Authorization", "message": "Authorization header là bắt buộc cho analyse-one."}],
            )

        try:
            watchlist_payload = await self.backend_client.get_watchlists(token=user_token)
            watchlist_items = self.watchlist_service.limit_items(self.watchlist_service.extract_items_from_backend_payload(watchlist_payload))
            allowed_symbols = [item["symbol"] for item in watchlist_items]
            data_sources.append(DataSourceStatus(name="Backend /api/watchlists", type="backend_api", status="success"))
        except Exception as exc:
            message, code, error_type = self._watchlist_error_response(exc)
            data_sources.append(DataSourceStatus(name="Backend /api/watchlists", type="backend_api", status="failed", detail=self._safe_error_detail(exc)))
            return api_error(
                message,
                error_type,
                code=code,
                details=[{"field": "watchlists", "message": self._safe_error_detail(exc)}],
            )

        if not allowed_symbols:
            return api_error(
                "Watchlists đang trống nên không thể xác minh quyền phân tích mã cổ phiếu.",
                "WATCHLIST_EMPTY",
                code=403,
                details=[{"field": "watchlists", "message": "Không tìm thấy mã cổ phiếu nào trong watchlists của người dùng."}],
            )

        is_allowed, symbol = self.watchlist_service.validate_symbol_allowed(
            symbol,
            allowed_symbols,
            requested_exchange=payload.scope_exchange,
            allowed_items=watchlist_items,
        )
        if self.settings.analyse_one_symbol_only and not is_allowed:
            return api_error(
                "Mã này không nằm trong watchlists nên không thể phân tích.",
                "SYMBOL_NOT_IN_WATCHLIST",
                code=403,
                details=[{"field": "symbol", "message": f"{symbol} không nằm trong danh sách watchlists hợp lệ."}],
            )

        try:
            stock_detail, stock_source_warnings = await self._load_stock_detail_for_analysis(symbol, payload.scope_exchange, data_sources, user_token=user_token)
        except Exception as exc:
            if self._is_auth_error(exc):
                return api_error(
                    "Phiên đăng nhập đã hết hạn hoặc token không hợp lệ.",
                    "AUTH_INVALID",
                    code=401,
                    details=[{"field": "Authorization", "message": "Backend từ chối token khi tải dữ liệu cổ phiếu."}],
                )
            raise
        self._mark_watchlist_loaded(stock_detail)
        warnings.extend(stock_source_warnings)
        stock_detail, company_fallback_warnings = await self._apply_company_fallback(symbol, payload.scope_exchange, stock_detail, data_sources)
        warnings.extend(company_fallback_warnings)
        stock_detail, financial_fallback_warnings = await self._apply_financial_fallback(symbol, payload.scope_exchange, stock_detail, data_sources)
        warnings.extend(financial_fallback_warnings)
        stock_detail, peer_fallback_warnings = await self._apply_peer_fallback(symbol, payload.scope_exchange, stock_detail, data_sources, user_token=user_token)
        warnings.extend(peer_fallback_warnings)
        warnings = self._merge_string_lists([], warnings)
        await self._save_backend_debug_artifacts(symbol, user_token=user_token)

        company = self.stock_data_service.extract_company(stock_detail)
        should_include_external_research = payload.options.include_external_research or self.settings.enable_external_research
        if should_include_external_research:
            try:
                research_context = await self.research_service.search(symbol=symbol, company=company)
            except Exception as exc:
                research_context = ExternalResearchContext(
                    enabled=True,
                    status="failed",
                    items=[],
                    flag_summary={"warnings": [str(exc)]},
                    source_statuses=[{"name": "External Research", "status": "failed", "detail": str(exc)}],
                    note="Không lấy được tin tức bên ngoài; cần kiểm tra thêm.",
                )
                warnings.append(f"External research lỗi: {exc}")
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
        self._save_market_context_debug(symbol, summary)

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
        warnings = self._merge_string_lists(warnings, llm_result.warnings)
        llm_markdown_content: str | None = None
        if llm_result.status == "success":
            summary, llm_markdown_content = self._merge_llm_output(summary, llm_result.data)

        timestamp = timestamp_for_filename(self.settings.analyse_timezone)
        report_id = f"{symbol}_{payload.scope_exchange}_{timestamp}"
        markdown_content = None
        markdown_output_path = None
        if payload.options.render_markdown or payload.options.render_html:
            llm_narrative = self.markdown_service.finalize_content(llm_markdown_content, summary)
            markdown_content = self.markdown_service.build(summary, llm_narrative=llm_narrative)

        if payload.options.render_markdown:
            if self.settings.report_write_markdown:
                try:
                    markdown_output_path = self.report_file_service.write_markdown(report_id, markdown_content)
                except Exception as exc:
                    warnings = self._merge_string_lists(warnings, [f"Không ghi được Markdown report: {exc}"])
                else:
                    pass
            else:
                warnings = self._merge_string_lists(warnings, ["Không xuất Markdown vì REPORT_WRITE_MARKDOWN=false."])
        else:
            warnings = self._merge_string_lists(warnings, ["Không xuất Markdown vì options.renderMarkdown=false."])
        markdown_report = MarkdownReport(
            available=bool(markdown_output_path),
            output_path=markdown_output_path,
            content=markdown_content if payload.options.render_markdown and self.settings.report_include_markdown_content_in_response else None,
        )
        html_report = HtmlReport()
        html_content = None
        html_output_path = None
        if payload.options.render_html:
            if self.settings.report_write_html:
                try:
                    html_data_sources = sanitize_data_source_statuses([source.model_dump() for source in data_sources])
                    html_content = self.html_service.build(
                        report_id,
                        summary,
                        markdown_content=markdown_content or "",
                        data_sources=html_data_sources,
                        provider={
                            "name": provider_name,
                            "model": llm_result.model,
                            "status": llm_result.status,
                            "latency_ms": llm_result.latency_ms,
                        },
                    )
                    html_output_path = self.report_file_service.write_html(report_id, html_content)
                except Exception as exc:
                    warnings = self._merge_string_lists(warnings, [f"Không tạo/ghi được HTML report: {exc}"])
                else:
                    pass
            else:
                warnings = self._merge_string_lists(warnings, ["Không xuất HTML vì REPORT_WRITE_HTML=false."])
            html_report = HtmlReport(
                available=bool(html_output_path),
                output_path=html_output_path,
                content=html_content if self.settings.report_include_html_content_in_response else None,
                template_name="HtmlService.build" if html_output_path else None,
            )
        else:
            warnings = self._merge_string_lists(warnings, ["Không xuất HTML vì options.renderHtml=false."])

        research_warnings = self._string_list((research_context.flag_summary or {}).get("warnings"))
        warnings = self._merge_string_lists(warnings, research_warnings)
        user_data_sources = sanitize_data_source_statuses([source.model_dump() for source in data_sources])
        self._save_data_sources_debug(symbol, data_sources, user_data_sources)

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
                data_sources=user_data_sources,
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

    async def _load_stock_detail_for_analysis(
        self,
        symbol: str,
        scope_exchange: str,
        data_sources: list[DataSourceStatus],
        *,
        user_token: str,
    ) -> tuple[dict, list[str]]:
        warnings: list[str] = []
        source_success = {
            "analysis_data_loaded": False,
            "backend_stock_detail_loaded": False,
            "chart_loaded": False,
        }
        if self.settings.backend_use_analysis_data_endpoint and hasattr(self.backend_client, "get_stock_analysis_data"):
            try:
                stock_payload = await self.backend_client.get_stock_analysis_data(
                    symbol=symbol,
                    token=user_token,
                    exchange=scope_exchange,
                    quarters=self.settings.backend_analysis_data_quarters,
                    chart_range=self.settings.backend_analysis_data_chart_range,
                    include_peers=self.settings.backend_analysis_data_include_peers,
                    include_market_context=self.settings.backend_analysis_data_include_market_context,
                )
                stock_detail = self.stock_data_service.normalize_analysis_data(stock_payload)
                source_success["analysis_data_loaded"] = self._has_usable_stock_payload(stock_detail)
                source_success["chart_loaded"] = bool(stock_detail.get("price_history"))
                stock_detail["_source_success"] = source_success
                data_sources.append(
                    DataSourceStatus(
                        name="Backend /api/stocks/:symbol/analysis-data",
                        type="backend_api",
                        status="success",
                        detail=(
                            f"exchange={scope_exchange}; quarters={self.settings.backend_analysis_data_quarters}; "
                            f"chartRange={self.settings.backend_analysis_data_chart_range}"
                        ),
                    )
                )
                return stock_detail, warnings
            except Exception as exc:
                if self._is_auth_error(exc):
                    raise
                warnings = self._merge_string_lists(warnings, [f"Không gọi được analysis-data, đã fallback sang endpoint cũ. Chi tiết: {self._safe_error_detail(exc)}"])
                data_sources.append(
                    DataSourceStatus(
                        name="Backend /api/stocks/:symbol/analysis-data",
                        type="backend_api",
                        status="failed",
                        detail=self._safe_error_detail(exc),
                    )
                )

        try:
            stock_payload = await self.backend_client.get_stock_detail(symbol, token=user_token)
            stock_detail = self.stock_data_service.normalize_stock_detail(stock_payload)
            source_success["backend_stock_detail_loaded"] = self._has_usable_stock_payload(stock_detail)
            data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol", type="backend_api", status="success"))
        except Exception as exc:
            if self._is_auth_error(exc):
                raise
            stock_detail = {"symbol": symbol, "latest_market": {}, "financials": {"periods": []}, "_source_success": source_success}
            warnings = self._merge_string_lists(warnings, [f"Chưa gọi được /api/stocks/:symbol: {self._safe_error_detail(exc)}"])
            data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol", type="backend_api", status="failed", detail=self._safe_error_detail(exc)))

        if hasattr(self.backend_client, "get_stock_chart"):
            try:
                chart_range = self.settings.backend_analysis_data_chart_range or "3m"
                chart_payload = await self.backend_client.get_stock_chart(symbol, range_value=chart_range, token=user_token)
                stock_detail = self.stock_data_service.merge_chart_history(stock_detail, chart_payload)
                source_success["chart_loaded"] = bool(self.stock_data_service.normalize_stock_chart(chart_payload))
                data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol/chart", type="backend_api", status="success", detail=f"range={chart_range}"))
            except Exception as exc:
                if self._is_auth_error(exc):
                    raise
                warnings = self._merge_string_lists(warnings, [f"Chưa gọi được /api/stocks/:symbol/chart: {self._safe_error_detail(exc)}"])
                data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol/chart", type="backend_api", status="failed", detail=self._safe_error_detail(exc)))
        stock_detail["_source_success"] = source_success
        return self.stock_data_service.normalize_analysis_data(stock_detail), warnings

    async def _apply_company_fallback(
        self,
        symbol: str,
        scope_exchange: str,
        stock_detail: dict,
        data_sources: list[DataSourceStatus],
    ) -> tuple[dict, list[str]]:
        normalized = self.stock_data_service.normalize_analysis_data(stock_detail)
        if self._has_sufficient_company_profile(normalized):
            self._save_company_overview_debug(symbol, normalized)
            return normalized, []

        if not self.settings.enable_cafef_company_fallback:
            data_sources.append(
                DataSourceStatus(
                    name="CafeF thông tin doanh nghiệp",
                    type="external_company",
                    status="disabled",
                    detail="Nguồn thông tin doanh nghiệp chưa cấu hình",
                )
            )
            self._save_company_overview_debug(symbol, normalized)
            return normalized, []

        try:
            fallback_payload = await self.cafef_company_adapter.fetch(symbol, exchange=scope_exchange)
        except Exception as exc:
            detail = self._safe_error_detail(exc)
            data_sources.append(DataSourceStatus(name="CafeF thông tin doanh nghiệp", type="external_company", status="failed", detail=detail))
            self._save_company_overview_debug(symbol, normalized)
            return normalized, [f"Không lấy được thông tin doanh nghiệp CafeF: {detail}"]

        useful = any(
            fallback_payload.get(key)
            for key in (
                "company_name",
                "industry_level_1",
                "industry_level_2",
                "industry_level_3",
                "industry",
                "sector",
                "business_overview",
                "leadership",
                "ownership",
            )
        )
        status = self._company_fallback_status(fallback_payload, useful=useful)
        detail = self._company_fallback_detail(fallback_payload)
        if useful:
            normalized = self.stock_data_service.merge_company_fallback(normalized, fallback_payload)
        data_sources.append(DataSourceStatus(name="CafeF thông tin doanh nghiệp", type="external_company", status=status, detail=detail))
        self._save_company_overview_debug(symbol, normalized)
        warnings = self._merge_string_lists(
            self._string_list((fallback_payload or {}).get("warnings")),
            self._string_list((fallback_payload or {}).get("technical_warnings")),
        )
        return normalized, warnings

    def _company_fallback_status(self, fallback_payload: dict, *, useful: bool) -> str:
        raw_status = str((fallback_payload or {}).get("status") or "partial").lower()
        if raw_status in {"disabled", "failed", "insufficient"}:
            return raw_status
        if not useful:
            return "insufficient"
        company_name = fallback_payload.get("company_name")
        has_governance = bool(fallback_payload.get("leadership") or fallback_payload.get("ownership"))
        if company_name and has_governance:
            return "success"
        return "partial"

    def _company_fallback_detail(self, fallback_payload: dict) -> str:
        source_url = (fallback_payload or {}).get("source_url") or "CafeF"
        accepted = fallback_payload.get("accepted_fields") if isinstance(fallback_payload, dict) else []
        accepted_count = len(accepted) if isinstance(accepted, list) else 0
        leadership_count = len(fallback_payload.get("leadership") or []) if isinstance(fallback_payload, dict) else 0
        ownership_count = len(fallback_payload.get("ownership") or []) if isinstance(fallback_payload, dict) else 0
        debug = fallback_payload.get("debug") if isinstance(fallback_payload.get("debug"), dict) else {}
        reason = debug.get("failure_reason") or "; ".join(self._string_list(fallback_payload.get("rejection_reasons")))[:180]
        detail = (
            f"Nguồn thông tin doanh nghiệp; {source_url}; fields={accepted_count}; "
            f"leadership_rows={leadership_count}; ownership_rows={ownership_count}"
        )
        if reason:
            detail += f"; reason={reason}"
        return detail

    def _has_sufficient_company_profile(self, normalized: dict) -> bool:
        overview = normalized.get("company_overview") if isinstance(normalized.get("company_overview"), dict) else {}
        peer_context = normalized.get("industry_peer_context") if isinstance(normalized.get("industry_peer_context"), dict) else {}
        industry = peer_context.get("industry") if isinstance(peer_context.get("industry"), dict) else {}
        has_company = bool(normalized.get("company") or overview.get("company_name"))
        has_business_overview = bool(overview.get("business_overview"))
        has_governance = bool(overview.get("leadership") or overview.get("ownership"))
        sector = industry.get("industry_level_1") or industry.get("sector") or industry.get("sector_name") or overview.get("industry_level_1") or overview.get("sector")
        group = industry.get("industry_level_2") or industry.get("industry_group") or industry.get("group") or overview.get("industry_level_2")
        detail = industry.get("industry_level_3") or industry.get("industry") or industry.get("industry_name") or overview.get("industry_level_3") or overview.get("industry")
        if has_company and has_business_overview and has_governance:
            return True
        return bool(has_company and detail and (sector or group) and has_governance)

    def _save_company_overview_debug(self, symbol: str, normalized: dict) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        try:
            payload = {
                "symbol": normalize_symbol(symbol),
                "company": normalized.get("company"),
                "company_overview": normalized.get("company_overview") if isinstance(normalized.get("company_overview"), dict) else {},
                "industry": (
                    normalized.get("industry_peer_context", {}).get("industry")
                    if isinstance(normalized.get("industry_peer_context"), dict)
                    else {}
                ),
                "company_fallback": normalized.get("_company_fallback") if isinstance(normalized.get("_company_fallback"), dict) else {},
            }
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_company_overview_normalized.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            merge_debug = normalized.get("_leadership_ownership_merge")
            if not isinstance(merge_debug, dict):
                overview = normalized.get("company_overview") if isinstance(normalized.get("company_overview"), dict) else {}
                _, merge_debug = self.stock_data_service.enrich_leadership_with_ownership(overview)
            (debug_dir / f"{normalize_symbol(symbol)}_leadership_ownership_merge.json").write_text(
                json.dumps(merge_debug, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _save_market_context_debug(self, symbol: str, summary: dict[str, Any]) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        try:
            payload = summary.get("market_context_debug") if isinstance(summary.get("market_context_debug"), dict) else {}
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_market_context_normalized.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _save_cafef_financial_attempt_debug(self, symbol: str, payload: dict[str, Any]) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        allowed = {
            "enabled": bool(payload.get("enabled")),
            "attempted": bool(payload.get("attempted")),
            "url": payload.get("url") or "",
            "status": payload.get("status"),
            "periods_found": payload.get("periods_found") or 0,
            "metrics_found": payload.get("metrics_found") if isinstance(payload.get("metrics_found"), list) else [],
            "timeout_ms": payload.get("timeout_ms") or self.settings.cafef_financial_timeout_ms,
            "fallback_used": bool(payload.get("fallback_used")),
        }
        if payload.get("error_type"):
            allowed["error_type"] = str(payload.get("error_type"))
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_financial_attempt.json").write_text(
                json.dumps(allowed, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _cafef_payload_timed_out(self, payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        text = " ".join(
            self._merge_string_lists(
                self._string_list(payload.get("warnings")),
                self._string_list(payload.get("technical_warnings")),
            )
        ).lower()
        return "timed out" in text or "timeout" in text or "quá thời gian" in text

    def _financial_metrics_found(self, periods: list[dict[str, Any]]) -> list[str]:
        metrics: set[str] = set()
        for period in periods:
            if not isinstance(period, dict):
                continue
            for key, value in period.items():
                if key in {"period", "year", "quarter", "source", "source_url"}:
                    continue
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    metrics.add(key)
        return sorted(metrics)

    async def _apply_financial_fallback(
        self,
        symbol: str,
        scope_exchange: str,
        stock_detail: dict,
        data_sources: list[DataSourceStatus],
    ) -> tuple[dict, list[str]]:
        normalized = self.stock_data_service.normalize_analysis_data(stock_detail)
        financials = normalized.get("financials") if isinstance(normalized.get("financials"), dict) else {}
        periods = financials.get("periods") if isinstance(financials.get("periods"), list) else []
        has_primary_financials = bool(self.stock_data_service.valid_financial_periods(periods))

        warnings: list[str] = []

        if self.settings.effective_enable_vietstock_financial_fallback and not has_primary_financials:
            try:
                fallback_payload = await self.vietstock_financial_adapter.fetch(symbol)
            except Exception as exc:
                detail = self._safe_error_detail(exc)
                data_sources.append(DataSourceStatus(name="Vietstock Finance BCTC", type="external_financial", status="failed", detail=detail))
                warnings = self._merge_string_lists(warnings, [f"Không lấy được dữ liệu tài chính Vietstock Finance: {detail}"])
            else:
                fallback_periods = fallback_payload.get("periods") if isinstance(fallback_payload, dict) else []
                fallback_warnings = self._merge_string_lists(
                    self._string_list((fallback_payload or {}).get("warnings")),
                    self._string_list((fallback_payload or {}).get("technical_warnings")),
                )
                valid_periods = self.stock_data_service.valid_financial_periods(fallback_periods if isinstance(fallback_periods, list) else [])
                raw_status = fallback_payload.get("status") or "partial"
                if valid_periods:
                    status = raw_status if raw_status in {"success", "partial", "insufficient", "disabled", "failed"} else "success"
                else:
                    status = "insufficient" if raw_status not in {"failed", "disabled"} else raw_status
                source_url = fallback_payload.get("source_url") or "Vietstock Finance"
                periods_count = len(valid_periods)
                detail = f"{source_url}; periods={periods_count}"
                if valid_periods:
                    normalized = self.stock_data_service.merge_financial_fallback(normalized, fallback_payload)
                data_sources.append(DataSourceStatus(name="Vietstock Finance BCTC", type="external_financial", status=status, detail=detail))
                warnings = self._merge_string_lists(warnings, fallback_warnings)
                if valid_periods:
                    has_primary_financials = True
        elif not self.settings.effective_enable_vietstock_financial_fallback:
            data_sources.append(
                DataSourceStatus(
                    name="Vietstock Finance BCTC",
                    type="external_financial",
                    status="disabled",
                    detail="ENABLE_VIETSTOCK_BCTC_FALLBACK=false",
                )
            )

        if self.settings.enable_cafef_financial_fallback:
            cafef_attempt: dict[str, Any] = {
                "enabled": True,
                "attempted": True,
                "url": "",
                "status": "failed",
                "periods_found": 0,
                "metrics_found": [],
                "timeout_ms": self.settings.cafef_financial_timeout_ms,
                "fallback_used": has_primary_financials,
            }
            try:
                cafef_payload = await self.cafef_financial_adapter.fetch(symbol, exchange=scope_exchange)
            except Exception as exc:
                detail = self._safe_error_detail(exc)
                cafef_attempt.update({"status": "failed", "error_type": exc.__class__.__name__})
                self._save_cafef_financial_attempt_debug(symbol, cafef_attempt)
                data_sources.append(DataSourceStatus(name="CafeF tài chính", type="external_financial", status="failed", detail=detail))
                warnings.append(f"Không lấy được dữ liệu tài chính CafeF: {detail}")
            else:
                cafef_periods = cafef_payload.get("periods") if isinstance(cafef_payload, dict) else []
                valid_cafef_periods = self.stock_data_service.valid_financial_periods(cafef_periods if isinstance(cafef_periods, list) else [])
                raw_status = cafef_payload.get("status") or "partial"
                cafef_warnings = self._merge_string_lists(
                    self._string_list((cafef_payload or {}).get("warnings")),
                    self._string_list((cafef_payload or {}).get("technical_warnings")),
                )
                if self._cafef_payload_timed_out(cafef_payload):
                    status = "failed"
                elif valid_cafef_periods:
                    status = raw_status if raw_status in {"success", "partial", "insufficient", "disabled", "failed"} else "success"
                else:
                    status = "insufficient" if raw_status not in {"failed", "disabled"} else raw_status
                detail = f"{cafef_payload.get('source_url') or 'CafeF'}; periods={len(valid_cafef_periods)}; attempted=true"
                if valid_cafef_periods:
                    normalized = self.stock_data_service.merge_financial_fallback(normalized, cafef_payload)
                cafef_attempt.update(
                    {
                        "url": cafef_payload.get("source_url") or "",
                        "status": status,
                        "periods_found": len(valid_cafef_periods),
                        "metrics_found": self._financial_metrics_found(valid_cafef_periods),
                    }
                )
                self._save_cafef_financial_attempt_debug(symbol, cafef_attempt)
                data_sources.append(DataSourceStatus(name="CafeF tài chính", type="external_financial", status=status, detail=detail))
                warnings = self._merge_string_lists(warnings, cafef_warnings)
        else:
            data_sources.append(
                DataSourceStatus(
                    name="CafeF tài chính",
                    type="external_financial",
                    status="disabled",
                    detail="ENABLE_CAFEF_FINANCIAL_FALLBACK=false",
                )
            )
            self._save_cafef_financial_attempt_debug(
                symbol,
                {
                    "enabled": False,
                    "attempted": False,
                    "url": "",
                    "status": "disabled",
                    "periods_found": 0,
                    "metrics_found": [],
                    "timeout_ms": self.settings.cafef_financial_timeout_ms,
                    "fallback_used": has_primary_financials,
                },
            )
        return normalized, warnings

    async def _apply_peer_fallback(
        self,
        symbol: str,
        scope_exchange: str,
        stock_detail: dict,
        data_sources: list[DataSourceStatus],
        *,
        user_token: str,
    ) -> tuple[dict, list[str]]:
        normalized = self.stock_data_service.normalize_analysis_data(stock_detail)
        peer_context = normalized.get("industry_peer_context") if isinstance(normalized.get("industry_peer_context"), dict) else {}
        existing_peers = peer_context.get("peers") if isinstance(peer_context.get("peers"), list) else []
        existing_valid_peers = self.stock_data_service.valid_peers(existing_peers, symbol=symbol)
        if existing_valid_peers:
            if self.settings.enable_peer_web_enrichment and any(self._peer_needs_enrichment(peer) for peer in existing_valid_peers):
                fallback_payload = {
                    "source": peer_context.get("source") or "Dữ liệu so sánh nội bộ",
                    "source_url": peer_context.get("source_url"),
                    "peers": existing_valid_peers,
                    "industry": peer_context.get("industry") if isinstance(peer_context.get("industry"), dict) else {},
                    "status": "partial",
                }
                enriched_payload = await self._enrich_peer_payload(symbol, scope_exchange, fallback_payload, user_token=user_token)
                peer_context = dict(peer_context)
                peer_context["peers"] = enriched_payload.get("peers") or existing_valid_peers
                normalized["industry_peer_context"] = peer_context
                recommendation = dict(normalized.get("same_industry_recommendation") if isinstance(normalized.get("same_industry_recommendation"), dict) else {})
                if not isinstance(recommendation.get("candidates"), list) or not recommendation.get("candidates"):
                    ranked = self.stock_data_service._rank_peers(peer_context["peers"])  # Uses verified/enriched metrics only.
                    recommendation["method"] = "So sánh cùng ngành từ dữ liệu đã đối chiếu"
                    recommendation["candidates"] = [
                        self.stock_data_service._peer_to_candidate(peer)
                        for peer in ranked[: max(1, self.settings.peer_recommendation_top_n)]
                    ]
                    normalized["same_industry_recommendation"] = recommendation
                self._save_peer_enrichment_debug(symbol, enriched_payload, normalized)
            return normalized, []

        if not self.settings.enable_vietstock_peer_fallback:
            data_sources.append(
                DataSourceStatus(
                    name="Vietstock peer cùng ngành",
                    type="external_peer",
                    status="disabled",
                    detail="ENABLE_VIETSTOCK_PEER_FALLBACK=false",
                )
            )
            return normalized, []

        try:
            fallback_payload = await self.vietstock_peer_adapter.fetch(symbol)
        except Exception as exc:
            detail = self._safe_error_detail(exc)
            data_sources.append(DataSourceStatus(name="Vietstock peer cùng ngành", type="external_peer", status="failed", detail=detail))
            return normalized, [f"Không lấy được dữ liệu peer Vietstock Finance: {detail}"]

        fallback_peers = fallback_payload.get("peers") if isinstance(fallback_payload, dict) else []
        valid_peers = self.stock_data_service.valid_peers(fallback_peers if isinstance(fallback_peers, list) else [], symbol=symbol)
        if valid_peers and self.settings.enable_peer_web_enrichment:
            fallback_payload = await self._enrich_peer_payload(symbol, scope_exchange, fallback_payload, user_token=user_token)
            fallback_peers = fallback_payload.get("peers") if isinstance(fallback_payload, dict) else []
            valid_peers = self.stock_data_service.valid_peers(fallback_peers if isinstance(fallback_peers, list) else [], symbol=symbol)
        fallback_industry = fallback_payload.get("industry") if isinstance(fallback_payload, dict) else {}
        has_fallback_industry = isinstance(fallback_industry, dict) and bool(fallback_industry)
        warnings = self._merge_string_lists(
            self._string_list((fallback_payload or {}).get("warnings")),
            self._string_list((fallback_payload or {}).get("technical_warnings")),
        )
        raw_status = fallback_payload.get("status") or "partial"
        if valid_peers:
            status = "success" if any(not self._peer_missing_metrics(peer) for peer in valid_peers) else "partial"
        else:
            status = raw_status if raw_status in {"disabled", "failed", "insufficient"} else "insufficient"
        source_url = fallback_payload.get("source_url") or "Vietstock Finance"
        detail = self._peer_fallback_detail(fallback_payload, valid_peers, source_url=source_url)
        if valid_peers or has_fallback_industry:
            normalized = self.stock_data_service.merge_peer_fallback(
                normalized,
                fallback_payload,
                symbol=symbol,
                top_n=self.settings.peer_recommendation_top_n,
            )
        self._save_peer_enrichment_debug(symbol, fallback_payload, normalized)
        data_sources.append(DataSourceStatus(name="Vietstock peer cùng ngành", type="external_peer", status=status, detail=detail))
        return normalized, warnings

    def _peer_fallback_detail(self, fallback_payload: dict, valid_peers: list[dict], *, source_url: str) -> str:
        debug = fallback_payload.get("debug") if isinstance(fallback_payload.get("debug"), dict) else {}
        peer_count = len(valid_peers)
        raw_count = len(fallback_payload.get("peers") or []) if isinstance(fallback_payload, dict) else 0
        missing: list[str] = []
        for peer in valid_peers:
            missing.extend(self._peer_missing_metrics(peer))
        missing = sorted(set(missing))
        parts = [
            source_url,
            f"page_loaded={str(bool(fallback_payload)).lower()}",
            f"tables_found={debug.get('tables_found') or 0}",
            f"grid_rows_found={debug.get('grid_rows_found') or 0}",
            f"peer_rows_found={raw_count}",
            f"normalized_peers={peer_count}",
        ]
        if missing:
            parts.append("missing_metrics=" + ",".join(missing))
        reason = debug.get("failure_reason")
        if reason and not peer_count:
            parts.append(f"reason={reason}")
        return "; ".join(parts)

    async def _enrich_peer_payload(self, symbol: str, scope_exchange: str, fallback_payload: dict, *, user_token: str) -> dict:
        peers = fallback_payload.get("peers") if isinstance(fallback_payload, dict) else []
        if not isinstance(peers, list) or not peers:
            return fallback_payload
        max_peers = max(0, int(self.settings.peer_web_enrichment_max_peers or 0))
        if max_peers <= 0:
            return fallback_payload
        enriched_peers: list[dict] = []
        attempts: list[dict] = []
        for peer in peers[:max_peers]:
            if not isinstance(peer, dict):
                continue
            enriched, peer_attempts = await self._enrich_single_peer(peer, scope_exchange, user_token=user_token)
            enriched_peers.append(enriched)
            attempts.extend(peer_attempts)
        enriched_peers.extend(peer for peer in peers[max_peers:] if isinstance(peer, dict))
        payload = dict(fallback_payload)
        payload["peers"] = enriched_peers
        payload["peer_enrichment"] = {
            "enabled": True,
            "target_symbol": normalize_symbol(symbol),
            "max_peers": max_peers,
            "attempts": attempts,
        }
        return payload

    async def _enrich_single_peer(self, peer: dict, scope_exchange: str, *, user_token: str) -> tuple[dict, list[dict]]:
        enriched = dict(peer)
        peer_symbol = normalize_symbol(enriched.get("symbol") or enriched.get("ticker"))
        attempts: list[dict] = []
        if not peer_symbol or not self._peer_needs_enrichment(enriched):
            self._finalize_peer_missing_metrics(enriched)
            return enriched, attempts
        exchange = str(enriched.get("exchange") or scope_exchange or "HOSE").strip() or "HOSE"

        backend_payload = await self._try_peer_source(
            peer_symbol,
            "Backend analysis-data",
            lambda: self.backend_client.get_stock_analysis_data(
                symbol=peer_symbol,
                token=user_token,
                exchange=exchange,
                quarters=2,
                chart_range=self.settings.backend_analysis_data_chart_range,
                include_peers=False,
                include_market_context=False,
            ),
            attempts,
        )
        if isinstance(backend_payload, dict):
            normalized = self.stock_data_service.normalize_analysis_data(backend_payload)
            self._merge_peer_stock_detail(enriched, normalized, source="Backend analysis-data")

        vietstock_has_financial_periods = False
        if self._peer_needs_enrichment(enriched):
            vietstock_financial = await self._try_peer_source(
                peer_symbol,
                "Vietstock Finance BCTC",
                lambda: self.vietstock_financial_adapter.fetch(peer_symbol),
                attempts,
            )
            if isinstance(vietstock_financial, dict):
                self._merge_peer_financial_payload(enriched, vietstock_financial, source="Vietstock Finance BCTC")
                periods = vietstock_financial.get("periods") if isinstance(vietstock_financial.get("periods"), list) else []
                vietstock_has_financial_periods = bool(periods)

        if self._peer_needs_enrichment(enriched) and not vietstock_has_financial_periods:
            cafef_financial = await self._try_peer_source(
                peer_symbol,
                "CafeF BCTC",
                lambda: self.cafef_financial_adapter.fetch(peer_symbol, exchange=exchange),
                attempts,
            )
            if isinstance(cafef_financial, dict):
                self._merge_peer_financial_payload(enriched, cafef_financial, source="CafeF BCTC")

        if not (enriched.get("company") or enriched.get("company_name")):
            company_payload = await self._try_peer_source(
                peer_symbol,
                "CafeF thông tin doanh nghiệp",
                lambda: self.cafef_company_adapter.fetch(peer_symbol, exchange=exchange),
                attempts,
            )
            if isinstance(company_payload, dict):
                self._merge_peer_company_payload(enriched, company_payload)

        self._finalize_peer_missing_metrics(enriched)
        return enriched, attempts

    async def _try_peer_source(self, peer_symbol: str, source_name: str, factory: object, attempts: list[dict]) -> object | None:
        attempt = {"symbol": peer_symbol, "source": source_name, "status": "failed"}
        try:
            timeout = max(1, int(self.settings.peer_web_enrichment_timeout_ms or 30000)) / 1000
            payload = await asyncio.wait_for(factory(), timeout=timeout)  # type: ignore[misc]
        except Exception as exc:
            attempt["error"] = self._safe_error_detail(exc)
            attempts.append(attempt)
            return None
        attempt["status"] = "success" if payload else "partial"
        if isinstance(payload, dict):
            attempt["source_url"] = payload.get("source_url")
            attempt["status"] = payload.get("status") or attempt["status"]
        attempts.append(attempt)
        return payload

    def _merge_peer_stock_detail(self, peer: dict, detail: dict, *, source: str) -> None:
        self._set_missing(peer, "company", detail.get("company"))
        self._set_missing(peer, "exchange", detail.get("exchange"))
        latest = detail.get("latest_market") if isinstance(detail.get("latest_market"), dict) else {}
        balance = detail.get("financial_balance") if isinstance(detail.get("financial_balance"), dict) else {}
        for target, keys in {
            "close_price": ("close_price", "close", "price"),
            "price": ("close_price", "close", "price"),
            "market_cap_billion": ("market_cap_billion", "market_cap", "marketCap"),
            "market_cap": ("market_cap_billion", "market_cap", "marketCap"),
            "eps_4q": ("eps_4q", "eps_ttm", "eps"),
            "pe_basic": ("pe", "pe_ratio"),
            "pe": ("pe", "pe_ratio"),
            "pb": ("pb", "pb_ratio"),
            "roe": ("roe",),
            "roa": ("roa",),
            "liquidity": ("matched_value_billion", "liquidity", "trading_value"),
        }.items():
            self._set_missing(peer, target, self._first_nested_value(latest, balance, *keys))
        self._add_peer_source(peer, source, None)

    def _merge_peer_company_payload(self, peer: dict, payload: dict) -> None:
        self._set_missing(peer, "company", payload.get("company_name"))
        self._set_missing(peer, "exchange", payload.get("exchange"))
        self._set_missing(peer, "industry", payload.get("industry_level_3") or payload.get("industry_level_2") or payload.get("industry"))
        self._add_peer_source(peer, payload.get("source") or "CafeF thông tin doanh nghiệp", payload.get("source_url"))

    def _merge_peer_financial_payload(self, peer: dict, payload: dict, *, source: str) -> None:
        periods = payload.get("periods") if isinstance(payload, dict) else []
        latest = periods[0] if isinstance(periods, list) and periods and isinstance(periods[0], dict) else {}
        self._set_missing(peer, "eps_4q", latest.get("eps") or latest.get("eps_ttm"))
        for key in ("pe", "pb", "roe", "roa"):
            self._set_missing(peer, key, latest.get(key))
        self._set_missing(peer, "pe_basic", latest.get("pe"))
        self._add_peer_source(peer, payload.get("source") or source, payload.get("source_url"))

    def _peer_needs_enrichment(self, peer: dict) -> bool:
        return bool(self._peer_missing_metrics(peer))

    def _peer_missing_metrics(self, peer: dict) -> list[str]:
        labels = []
        checks = (
            ("Doanh nghiệp", peer.get("company") or peer.get("company_name")),
            ("Giá", peer.get("close_price") or peer.get("price")),
            ("Vốn hóa", peer.get("market_cap_billion") or peer.get("market_cap")),
            ("P/E", peer.get("pe_basic") or peer.get("pe")),
            ("P/B", peer.get("pb")),
            ("ROE", peer.get("roe")),
        )
        for label, value in checks:
            if value in (None, "", [], {}):
                labels.append(label)
        return labels

    def _finalize_peer_missing_metrics(self, peer: dict) -> None:
        missing = self._peer_missing_metrics(peer)
        peer["missing_metrics"] = missing
        if missing:
            peer["missing_data"] = ", ".join(missing)
            peer["data_note"] = (
                f"Thiếu {', '.join(missing)} sau khi đối chiếu các nguồn công khai có cấu hình; "
                "vẫn có thể dùng mã này làm peer định tính nếu cùng nhóm ngành."
            )
            peer["quantitative_label"] = "Cần bổ sung: " + ", ".join(missing[:4])
        else:
            peer["missing_data"] = ""
            peer["data_note"] = "Có đủ dữ liệu giá, định giá và sinh lời cơ bản để so sánh sơ bộ."
            peer.pop("quantitative_label", None)
        peer["confidence"] = max(self._safe_float(peer.get("confidence")), self._peer_confidence(peer))

    def _peer_confidence(self, peer: dict) -> float:
        metric_count = sum(
            1
            for key in ("close_price", "price", "market_cap_billion", "market_cap", "eps_4q", "pe_basic", "pe", "pb", "roe")
            if peer.get(key) not in (None, "")
        )
        score = 0.48 + min(metric_count, 6) * 0.06
        if peer.get("company") or peer.get("company_name"):
            score += 0.08
        if peer.get("enrichment_sources"):
            score += 0.05
        return round(min(score, 0.86), 2)

    def _set_missing(self, data: dict, key: str, value: object) -> None:
        if value in (None, "", [], {}):
            return
        if data.get(key) in (None, "", [], {}):
            data[key] = value

    def _first_nested_value(self, primary: dict, secondary: dict, *keys: str) -> object | None:
        for data in (primary, secondary):
            if not isinstance(data, dict):
                continue
            for key in keys:
                if data.get(key) not in (None, "", [], {}):
                    return data.get(key)
        return None

    def _safe_float(self, value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _add_peer_source(self, peer: dict, source: object, url: object | None) -> None:
        sources = peer.get("enrichment_sources") if isinstance(peer.get("enrichment_sources"), list) else []
        item = {"source": str(source or "Nguồn công khai")}
        if url:
            item["source_url"] = str(url)
        if item not in sources:
            sources.append(item)
        peer["enrichment_sources"] = sources

    def _save_peer_enrichment_debug(self, symbol: str, fallback_payload: dict, normalized: dict) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            peers = fallback_payload.get("peers") if isinstance(fallback_payload.get("peers"), list) else []
            recommendation = normalized.get("same_industry_recommendation") if isinstance(normalized.get("same_industry_recommendation"), dict) else {}
            candidates = recommendation.get("candidates") if isinstance(recommendation.get("candidates"), list) else []
            (debug_dir / f"{normalize_symbol(symbol)}_peer_enrichment.json").write_text(
                json.dumps(
                    {
                        "symbol": normalize_symbol(symbol),
                        "enabled": self.settings.enable_peer_web_enrichment,
                        "source_url": fallback_payload.get("source_url"),
                        "enrichment_attempts": (fallback_payload.get("peer_enrichment") or {}).get("attempts") or [],
                        "peers": peers,
                        "missing_metrics_per_peer": {
                            peer.get("symbol"): peer.get("missing_metrics") for peer in peers if isinstance(peer, dict)
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_same_industry_candidates.json").write_text(
                json.dumps(
                    {"symbol": normalize_symbol(symbol), "final_candidates": candidates},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        except Exception:
            return

    def _watchlist_error_response(self, exc: Exception) -> tuple[str, int, str]:
        if self._is_auth_error(exc):
            return "Phiên đăng nhập đã hết hạn hoặc token không hợp lệ.", 401, "AUTH_INVALID"
        return "Không tải được watchlists để xác minh quyền phân tích mã cổ phiếu.", 502, "WATCHLIST_UNAVAILABLE"

    def _is_auth_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        category = str(getattr(exc, "category", "") or "").lower()
        detail = self._safe_error_detail(exc).lower()
        return status_code == 401 or category == "unauthorized" or "401" in detail or "unauthorized" in detail

    def _has_usable_stock_payload(self, payload: dict) -> bool:
        if not isinstance(payload, dict):
            return False
        normalized = self.stock_data_service.normalize_analysis_data(payload)
        return bool(
            normalized.get("symbol")
            or normalized.get("company")
            or normalized.get("latest_market")
            or normalized.get("price_history")
            or (normalized.get("financials") or {}).get("periods")
        )

    def _mark_watchlist_loaded(self, stock_detail: dict) -> None:
        if not isinstance(stock_detail, dict):
            return
        source_success = stock_detail.get("_source_success")
        if not isinstance(source_success, dict):
            source_success = {}
        source_success["watchlist_loaded"] = True
        stock_detail["_source_success"] = source_success

    def _safe_error_detail(self, exc: Exception) -> str:
        detail = str(exc)
        if len(detail) > 300:
            detail = detail[:297] + "..."
        return detail

    async def _save_backend_debug_artifacts(self, symbol: str, *, user_token: str | None = None) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            config_payload = await ConfigDiagnosticService(self.settings, self.backend_client).build(check_backend=False)
            (debug_dir / f"{symbol}_config_check.json").write_text(
                json.dumps(config_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            backend_payload = {
                "base_url": self.backend_client.base_url,
                "token_attached": bool(str(user_token or "").strip()),
                "analysis_data_url_example": self.backend_client.build_stock_analysis_data_url(
                    symbol,
                    exchange="HOSE",
                    quarters=self.settings.backend_analysis_data_quarters,
                    chart_range=self.settings.backend_analysis_data_chart_range,
                    include_peers=self.settings.backend_analysis_data_include_peers,
                    include_market_context=self.settings.backend_analysis_data_include_market_context,
                ),
                "calls": self.backend_client.sanitized_diagnostics(),
            }
            (debug_dir / f"{symbol}_backend_urls.json").write_text(
                json.dumps(backend_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            return

    def _save_data_sources_debug(self, symbol: str, raw_sources: list[DataSourceStatus], user_sources: list[dict]) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            raw_payload = [source.model_dump() if hasattr(source, "model_dump") else source for source in raw_sources]
            payload = {
                "symbol": normalize_symbol(symbol),
                "user_facing_sources": user_sources,
                "source_mapping": build_data_source_debug_rows(raw_payload, user_sources),
            }
            (debug_dir / f"{normalize_symbol(symbol)}_user_facing_sources_debug.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            return

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
