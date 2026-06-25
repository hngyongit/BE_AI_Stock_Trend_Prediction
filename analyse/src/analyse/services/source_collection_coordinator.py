from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings, get_settings
from analyse.schemas.report import DataSourceStatus
from analyse.services.stock_data_service import StockDataService
from analyse.utils.debug_scrub import scrub_debug_text


@dataclass
class SourceCollectionResult:
    backend_stock_payload: dict[str, Any] | None = None
    backend_analysis_data: dict[str, Any] | None = None
    backend_stock_detail: dict[str, Any] | None = None
    backend_stock_chart: dict[str, Any] | None = None
    stock_detail: dict[str, Any] | None = None
    stock_chart: dict[str, Any] | None = None
    normalized_stock_payload: dict[str, Any] | None = None
    data_source_statuses: list[Any] = field(default_factory=list)
    cafef_company: dict[str, Any] | None = None
    cafef_financial: dict[str, Any] | None = None
    vietstock_financial: dict[str, Any] | None = None
    vietstock_peer: dict[str, Any] | None = None
    external_research: Any | None = None
    enriched_summary: dict[str, Any] | None = None
    source_backed_context: dict[str, Any] | None = None
    external_research_context: dict[str, Any] | None = None
    research_insights: dict[str, Any] | list[Any] | None = None
    evidence_table: list[Any] = field(default_factory=list)
    source_backed_warnings: list[str] = field(default_factory=list)
    source_backed_debug_payload: dict[str, Any] = field(default_factory=dict)
    source_statuses: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    debug_payload: dict[str, Any] = field(default_factory=dict)


class SourceCollectionCoordinator:
    """Future coordinator for analyse-one source loading.

    The live flow still stays in ReportService until each source block can move
    with focused regression tests.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        backend_client: BackendClient | None = None,
        stock_data_service: StockDataService | None = None,
        source_backed_enrichment_service: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.backend_client = backend_client or BackendClient(self.settings)
        self.stock_data_service = stock_data_service or StockDataService()
        self.source_backed_enrichment_service = source_backed_enrichment_service

    async def collect_for_analyse_one(
        self,
        *,
        symbol: str,
        exchange: str | None,
        token: str | None,
        options: Any,
    ) -> SourceCollectionResult:
        _ = (symbol, exchange, token, options)
        return SourceCollectionResult()

    async def collect_backend_stock_sources(
        self,
        *,
        symbol: str,
        exchange: str | None,
        token: str | None,
        chart_range: str | None = None,
        quarters: int | None = None,
        include_peers: bool | None = None,
        include_market_context: bool | None = None,
    ) -> SourceCollectionResult:
        warnings: list[str] = []
        data_sources: list[DataSourceStatus] = []
        source_success = {
            "analysis_data_loaded": False,
            "backend_stock_detail_loaded": False,
            "chart_loaded": False,
        }
        effective_chart_range = chart_range or self.settings.backend_analysis_data_chart_range or "3m"
        effective_quarters = quarters if quarters is not None else self.settings.backend_analysis_data_quarters
        effective_include_peers = (
            self.settings.backend_analysis_data_include_peers if include_peers is None else include_peers
        )
        effective_include_market_context = (
            self.settings.backend_analysis_data_include_market_context
            if include_market_context is None
            else include_market_context
        )

        if self.settings.backend_use_analysis_data_endpoint and hasattr(self.backend_client, "get_stock_analysis_data"):
            try:
                stock_payload = await self.backend_client.get_stock_analysis_data(
                    symbol=symbol,
                    token=token,
                    exchange=exchange,
                    quarters=effective_quarters,
                    chart_range=effective_chart_range,
                    include_peers=effective_include_peers,
                    include_market_context=effective_include_market_context,
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
                            f"exchange={exchange}; quarters={effective_quarters}; "
                            f"chartRange={effective_chart_range}"
                        ),
                    )
                )
                return self._result(
                    backend_stock_payload=stock_payload,
                    backend_analysis_data=stock_payload,
                    stock_detail=stock_detail,
                    normalized_stock_payload=stock_detail,
                    data_sources=data_sources,
                    warnings=warnings,
                    debug_payload={"source_success": source_success},
                )
            except Exception as exc:
                if self._is_auth_error(exc):
                    raise
                detail = self._safe_error_detail(exc)
                warnings = self._merge_string_lists(
                    warnings,
                    [f"Không gọi được analysis-data, đã fallback sang endpoint cũ. Chi tiết: {detail}"],
                )
                data_sources.append(
                    DataSourceStatus(
                        name="Backend /api/stocks/:symbol/analysis-data",
                        type="backend_api",
                        status="failed",
                        detail=detail,
                    )
                )

        try:
            stock_payload = await self.backend_client.get_stock_detail(symbol, token=token)
            stock_detail = self.stock_data_service.normalize_stock_detail(stock_payload)
            source_success["backend_stock_detail_loaded"] = self._has_usable_stock_payload(stock_detail)
            data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol", type="backend_api", status="success"))
        except Exception as exc:
            if self._is_auth_error(exc):
                raise
            detail = self._safe_error_detail(exc)
            stock_payload = None
            stock_detail = {"symbol": symbol, "latest_market": {}, "financials": {"periods": []}, "_source_success": source_success}
            warnings = self._merge_string_lists(warnings, [f"Chưa gọi được /api/stocks/:symbol: {detail}"])
            data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol", type="backend_api", status="failed", detail=detail))

        chart_payload: dict[str, Any] | None = None
        if hasattr(self.backend_client, "get_stock_chart"):
            try:
                chart_payload = await self.backend_client.get_stock_chart(symbol, range_value=effective_chart_range, token=token)
                stock_detail = self.stock_data_service.merge_chart_history(stock_detail, chart_payload)
                source_success["chart_loaded"] = bool(self.stock_data_service.normalize_stock_chart(chart_payload))
                data_sources.append(
                    DataSourceStatus(
                        name="Backend /api/stocks/:symbol/chart",
                        type="backend_api",
                        status="success",
                        detail=f"range={effective_chart_range}",
                    )
                )
            except Exception as exc:
                if self._is_auth_error(exc):
                    raise
                detail = self._safe_error_detail(exc)
                warnings = self._merge_string_lists(warnings, [f"Chưa gọi được /api/stocks/:symbol/chart: {detail}"])
                data_sources.append(DataSourceStatus(name="Backend /api/stocks/:symbol/chart", type="backend_api", status="failed", detail=detail))

        stock_detail["_source_success"] = source_success
        normalized = self.stock_data_service.normalize_analysis_data(stock_detail)
        return self._result(
            backend_stock_payload=stock_payload,
            backend_stock_detail=stock_payload,
            backend_stock_chart=chart_payload,
            stock_detail=normalized,
            stock_chart=chart_payload,
            normalized_stock_payload=normalized,
            data_sources=data_sources,
            warnings=warnings,
            debug_payload={"source_success": source_success},
        )

    async def collect_source_backed_enrichment(
        self,
        *,
        symbol: str,
        exchange: str | None,
        stock_payload: dict[str, Any],
        summary: dict[str, Any],
        research_context: Any | None = None,
        company_name: str | None = None,
        backend_source_result: SourceCollectionResult | None = None,
        token: str | None = None,
        options: Any | None = None,
    ) -> SourceCollectionResult:
        _ = (backend_source_result, token, options)
        effective_company_name = (
            company_name
            or self._company_name_from_payload(stock_payload)
            or self._company_name_from_payload(summary)
        )
        enrichment_service = self._source_backed_enrichment_service()
        enriched = await enrichment_service.enrich(
            symbol=symbol,
            exchange=exchange,
            company_name=effective_company_name,
            summary=summary,
            research_context=research_context,
        )
        source_backed_context = self._dict(enriched.get("source_backed_evidence"))
        external_research_context = self._external_research_context(enriched, research_context)
        presentation = self._dict(enriched.get("report_presentation"))
        research_insights = enriched.get("research_insights") or presentation.get("research_insights")
        evidence_table = self._list_any(enriched.get("evidence_table"))
        source_backed_warnings = self._string_list(source_backed_context.get("warnings"))
        debug_payload = {
            "evidence_count": len(evidence_table),
            "source_backed_warnings_count": len(source_backed_warnings),
        }
        return SourceCollectionResult(
            enriched_summary=enriched,
            source_backed_context=source_backed_context or None,
            external_research_context=external_research_context or None,
            research_insights=research_insights,
            evidence_table=evidence_table,
            source_backed_warnings=source_backed_warnings,
            source_backed_debug_payload=debug_payload,
        )

    def _result(
        self,
        *,
        backend_stock_payload: dict[str, Any] | None = None,
        backend_analysis_data: dict[str, Any] | None = None,
        backend_stock_detail: dict[str, Any] | None = None,
        backend_stock_chart: dict[str, Any] | None = None,
        stock_detail: dict[str, Any] | None = None,
        stock_chart: dict[str, Any] | None = None,
        normalized_stock_payload: dict[str, Any] | None = None,
        data_sources: list[Any] | None = None,
        warnings: list[str] | None = None,
        debug_payload: dict[str, Any] | None = None,
    ) -> SourceCollectionResult:
        source_statuses = list(data_sources or [])
        return SourceCollectionResult(
            backend_stock_payload=backend_stock_payload,
            backend_analysis_data=backend_analysis_data,
            backend_stock_detail=backend_stock_detail,
            backend_stock_chart=backend_stock_chart,
            stock_detail=stock_detail,
            stock_chart=stock_chart,
            normalized_stock_payload=normalized_stock_payload,
            data_source_statuses=source_statuses,
            source_statuses=list(source_statuses),
            warnings=list(warnings or []),
            debug_payload=dict(debug_payload or {}),
        )

    def _has_usable_stock_payload(self, payload: dict[str, Any]) -> bool:
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

    def _is_auth_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        category = str(getattr(exc, "category", "") or "").lower()
        detail = self._safe_error_detail(exc).lower()
        return status_code == 401 or category == "unauthorized" or "401" in detail or "unauthorized" in detail

    def _safe_error_detail(self, exc: Exception) -> str:
        detail = scrub_debug_text(str(exc))
        if len(detail) > 300:
            detail = detail[:297] + "..."
        return detail

    def _merge_string_lists(self, *values: Any) -> list[str]:
        merged: list[str] = []
        for value in values:
            items = value if isinstance(value, list) else [value]
            for item in items:
                if isinstance(item, str):
                    text = item.strip()
                    if text and text not in merged:
                        merged.append(text)
        return merged

    def _company_name_from_payload(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in ("company", "company_name", "companyName", "name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        overview = self._dict(payload.get("company_overview") or payload.get("companyOverview"))
        for key in ("company_name", "companyName", "name"):
            value = overview.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _source_backed_enrichment_service(self) -> Any:
        if self.source_backed_enrichment_service is None:
            from analyse.research.source_backed_enrichment_service import SourceBackedEnrichmentService

            self.source_backed_enrichment_service = SourceBackedEnrichmentService(self.settings)
        return self.source_backed_enrichment_service

    def _external_research_context(self, summary: dict[str, Any], research_context: Any | None) -> dict[str, Any]:
        context = self._dict(summary.get("external_research_context") or summary.get("externalResearchContext"))
        if context:
            return context
        if research_context is None:
            return {}
        model_dump = getattr(research_context, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            return dumped if isinstance(dumped, dict) else {}
        return research_context if isinstance(research_context, dict) else {}

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list_any(self, value: Any) -> list[Any]:
        return list(value) if isinstance(value, list) else []

    def _string_list(self, value: Any) -> list[str]:
        return [str(item).strip() for item in self._list_any(value) if str(item).strip()]
