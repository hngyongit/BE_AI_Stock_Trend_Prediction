from __future__ import annotations

from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.services.report_debug_service import ReportDebugService
from analyse.services.report_forecast_normalizer import ReportForecastNormalizer
from analyse.services.summary_service import SummaryService
from analyse.utils.symbol_utils import normalize_symbol


class ReportAssemblyService:
    """Future home for summary, presentation, and final response assembly."""

    def __init__(
        self,
        settings: Settings | None = None,
        summary_service: SummaryService | None = None,
        forecast_normalizer: ReportForecastNormalizer | None = None,
        report_debug_service: ReportDebugService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.summary_service = summary_service or SummaryService(settings=self.settings)
        self.forecast_normalizer = forecast_normalizer or ReportForecastNormalizer(self.settings)
        self.report_debug_service = report_debug_service or ReportDebugService(self.settings)

    async def build_report_summary_and_presentation(
        self,
        *,
        symbol: str,
        payload: Any,
        source_result: Any,
        llm_result: Any | None,
    ) -> dict[str, Any]:
        _ = (symbol, payload, source_result, llm_result)
        return {}

    def build_provider_metadata(
        self,
        *,
        provider: str | None,
        model: str | None,
        status: str = "not_implemented",
        latency_ms: int | None = 0,
    ) -> dict[str, Any]:
        return {
            "name": provider,
            "model": model,
            "status": status,
            "latency_ms": int(latency_ms or 0),
        }

    def refresh_summary_presentation(
        self,
        *,
        summary: dict[str, Any],
        research_context: Any | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = warnings
        existing_presentation = self._dict(summary.get("report_presentation"))
        refreshed = self.summary_service.refresh_report_presentation(
            summary,
            research_context=research_context,
        )
        if existing_presentation:
            presentation = self._dict(refreshed.get("report_presentation"))
            for key, value in existing_presentation.items():
                presentation.setdefault(key, value)
            refreshed["report_presentation"] = presentation
        return refreshed

    def enforce_mandatory_forecast_sections(
        self,
        *,
        symbol: str,
        summary: dict[str, Any],
        research_context: Any | None = None,
        warnings: list[str] | None = None,
        debug_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        _ = (warnings, debug_context)
        before_presentation = self.forecast_normalizer.presentation_counts(summary)
        normalized, debug = self.forecast_normalizer.normalize_summary(summary)
        normalized = self.refresh_summary_presentation(
            summary=normalized,
            research_context=research_context,
            warnings=warnings,
        )
        after_presentation = self.forecast_normalizer.presentation_counts(normalized)
        debug = {
            **debug,
            "presentation_before": before_presentation,
            "presentation_after": after_presentation,
            "response_validation_passed": (
                after_presentation["scenarios"] >= 3
                and after_presentation["checklist"] >= 5
                and after_presentation["action_rows"] >= 2
            ),
        }
        normalized["mandatory_forecast_sections_validation"] = debug
        self._save_mandatory_forecast_sections_debug(symbol, debug)
        return normalized, debug

    def _save_mandatory_forecast_sections_debug(self, symbol: str, payload: dict[str, Any]) -> None:
        if not self.report_debug_service.enabled:
            return
        try:
            clean_symbol = normalize_symbol(symbol) or "UNKNOWN"
            self.report_debug_service.write_symbol_json_artifact(
                symbol=clean_symbol,
                suffix="mandatory_forecast_sections_validation.json",
                payload={"symbol": clean_symbol, **payload},
            )
        except Exception:
            return

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}
