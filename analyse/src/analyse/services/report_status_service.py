from __future__ import annotations

from typing import Any

from analyse.utils.debug_scrub import scrub_debug_text


class ReportStatusService:
    """Derive report/source/history statuses without owning report assembly."""

    WARNING_STATUSES = {"partial", "failed"}
    PARTIAL_SOURCE_STATUSES = {"failed", "partial", "insufficient", "skipped", "disabled", "not_configured"}

    def build_report_status(
        self,
        *,
        has_report_content: bool,
        analysis_error: Exception | None = None,
        source_warnings: list[str] | None = None,
        history_warning: str | None = None,
        source_status: str | None = None,
        history_status: str | None = None,
    ) -> dict[str, Any]:
        warnings = self.safe_warning_list(source_warnings)
        if history_warning:
            warnings = self._append_unique(warnings, scrub_debug_text(history_warning))
        if analysis_error is not None:
            warnings = self._append_unique(warnings, scrub_debug_text(str(analysis_error)))

        analysis_status = "failed" if analysis_error is not None else "success"
        normalized_source_status = self._status_or_default(source_status, "success")
        normalized_history_status = self._status_or_default(history_status, "disabled")
        report_status = self.derive_report_status(
            analysis_status=analysis_status,
            history_status=normalized_history_status,
            source_status=normalized_source_status,
            warnings=warnings,
            has_report_content=has_report_content,
        )
        return {
            "report_status": report_status,
            "analysis_status": analysis_status,
            "source_status": normalized_source_status,
            "history_status": normalized_history_status,
            "warnings": warnings,
        }

    def aggregate_source_status(self, sources: list[dict]) -> str:
        if not sources:
            return "partial"
        statuses = {str(source.get("status") or "").strip().lower() for source in sources if isinstance(source, dict)}
        blocking_failures = {
            str(source.get("name") or "")
            for source in sources
            if isinstance(source, dict)
            and str(source.get("status") or "").strip().lower() == "failed"
            and str(source.get("type") or source.get("source_type") or "") == "backend"
        }
        if blocking_failures:
            return "failed"
        if statuses & self.PARTIAL_SOURCE_STATUSES:
            return "partial"
        return "success"

    def derive_report_status(
        self,
        *,
        analysis_status: str,
        history_status: str,
        source_status: str,
        warnings: list[str] | None,
        has_report_content: bool,
    ) -> str:
        if not has_report_content or analysis_status == "failed":
            return "failed"
        if history_status == "failed" or source_status in self.WARNING_STATUSES or warnings:
            return "success_with_warnings"
        return "success"

    def safe_warning_list(self, warnings: list[str] | None) -> list[str]:
        result: list[str] = []
        for warning in warnings or []:
            text = scrub_debug_text(str(warning))
            if text and text not in result:
                result.append(text)
        return result

    def _append_unique(self, warnings: list[str], warning: str) -> list[str]:
        if warning and warning not in warnings:
            warnings.append(warning)
        return warnings

    def _status_or_default(self, value: str | None, default: str) -> str:
        text = str(value or "").strip().lower()
        return text or default
