from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.utils.debug_scrub import scrub_debug_payload
from analyse.utils.symbol_utils import normalize_symbol


MISSING_VALUES = {"", None, "Chưa xác minh", "Chưa xác định"}


class ReportMissingFieldAuditor:
    """Audit final user-facing report JSON for avoidable missing placeholders."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def audit(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._dict(response.get("data"))
        summary = self._dict(data.get("summary"))
        presentation = self._dict(summary.get("report_presentation"))
        records: list[dict[str, Any]] = []

        self._audit_quick_overview(records, summary, presentation)
        self._audit_market_context(records, summary, presentation)
        self._audit_action_table(records, summary, presentation)
        self._audit_scenario_table(records, summary, presentation)
        self._audit_checklist(records, summary, presentation)
        self._audit_data_coverage(records, summary, presentation)
        self._audit_sources(records, data)
        return records

    def save_debug(self, symbol: str, response: dict[str, Any]) -> list[dict[str, Any]]:
        records = self.audit(response)
        if not self.settings.missing_field_enrichment_write_debug:
            return records
        try:
            clean_symbol = normalize_symbol(symbol) or normalize_symbol(self._dict(response.get("data")).get("symbol")) or "UNKNOWN"
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "symbol": clean_symbol,
                "audit_count": len(records),
                "records": records,
                "policy": self._dict(
                    self._dict(self._dict(self._dict(response.get("data")).get("summary")).get("report_presentation")).get(
                        "source_backed_enrichment"
                    )
                ),
            }
            (debug_dir / f"{clean_symbol}_missing_field_audit.json").write_text(
                json.dumps(self._scrub(payload), ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            return records
        return records

    def _audit_quick_overview(self, records: list[dict[str, Any]], summary: dict[str, Any], presentation: dict[str, Any]) -> None:
        quick = self._dict(presentation.get("quick_overview"))
        card = self._card_by_label(quick, "Biến động kỳ chart")
        if self._is_missing(card.get("value")) or card.get("status") == "missing":
            records.append(
                self._record(
                    "quick_overview",
                    "chart_period_change",
                    card.get("value"),
                    raw=bool(summary.get("price_history")),
                    normalized=bool(self._dict(summary.get("momentum")).get("chart_period_change_pct") is not None),
                    presentation=not self._is_missing(card.get("value")),
                    source_candidates=["price_history", "stock_chart"],
                    fix="mapping_missing" if summary.get("price_history") else "source_missing",
                )
            )

    def _audit_market_context(self, records: list[dict[str, Any]], summary: dict[str, Any], presentation: dict[str, Any]) -> None:
        view = self._dict(presentation.get("market_context_view"))
        card = self._card_by_label(view, "Giá trị giao dịch")
        if self._is_missing(card.get("value")) or card.get("status") == "missing":
            records.append(
                self._record(
                    "market_context",
                    "trading_value_billion",
                    card.get("value"),
                    raw=bool(summary.get("hose_market_context") or summary.get("market_general_context")),
                    normalized=bool(self._dict(self._dict(summary.get("market_context_debug")).get("normalized")).get("trading_value_billion")),
                    presentation=not self._is_missing(card.get("value")),
                    source_candidates=["hose_market_context", "market_general_context"],
                    fix="mapping_missing",
                )
            )

    def _audit_action_table(self, records: list[dict[str, Any]], summary: dict[str, Any], presentation: dict[str, Any]) -> None:
        rows = self._list(self._dict(presentation.get("action_table")).get("rows"))
        if not rows:
            records.append(
                self._record(
                    "action_plan",
                    "action_table.rows",
                    "Chưa có dữ liệu",
                    raw=bool(summary.get("investment_plan") or summary.get("scores") or summary.get("momentum")),
                    normalized=True,
                    presentation=False,
                    source_candidates=["summary.actionPlan", "investment_plan", "scores", "momentum"],
                    fix="safe_educational_fallback_missing",
                )
            )
            return
        for index, row in enumerate(rows):
            for field in ("action", "condition", "price_zone", "position_size", "stop_loss", "note"):
                if self._is_missing(row.get(field)):
                    records.append(
                        self._record(
                            "action_plan",
                            f"action_table.rows[{index}].{field}",
                            row.get(field),
                            raw=True,
                            normalized=True,
                            presentation=False,
                            source_candidates=["summary.actionPlan", "riskManagement", "watchPoints", "position_sizing"],
                            fix="safe_educational_fallback_missing",
                        )
                    )

    def _audit_scenario_table(self, records: list[dict[str, Any]], summary: dict[str, Any], presentation: dict[str, Any]) -> None:
        rows = self._list(self._dict(presentation.get("scenario_table")).get("rows"))
        if not rows:
            records.append(
                self._record(
                    "scenario",
                    "scenario_table.rows",
                    "Chưa có dữ liệu kịch bản.",
                    raw=bool(summary.get("scores") or summary.get("momentum") or summary.get("weaknesses")),
                    normalized=True,
                    presentation=False,
                    source_candidates=["trend", "scores", "market_context", "risks"],
                    fix="safe_educational_fallback_missing",
                )
            )

    def _audit_checklist(self, records: list[dict[str, Any]], summary: dict[str, Any], presentation: dict[str, Any]) -> None:
        items = self._list(self._dict(presentation.get("checklist")).get("items"))
        if not items:
            records.append(
                self._record(
                    "checklist",
                    "checklist.items",
                    "Chưa có checklist cho lần phân tích này.",
                    raw=bool(summary.get("weaknesses") or summary.get("scores") or summary.get("bctc_3q")),
                    normalized=True,
                    presentation=False,
                    source_candidates=["watchPoints", "riskManagement", "signals", "financial_table"],
                    fix="safe_workflow_fallback_missing",
                )
            )

    def _audit_data_coverage(self, records: list[dict[str, Any]], summary: dict[str, Any], presentation: dict[str, Any]) -> None:
        items = self._list(self._dict(presentation.get("data_coverage")).get("items"))
        for index, item in enumerate(items):
            if item.get("status") == "available" and self._is_missing(item.get("value")):
                records.append(
                    self._record(
                        "data_coverage",
                        f"items[{index}].value",
                        item.get("value"),
                        raw=bool(summary.get("data_coverage")),
                        normalized=True,
                        presentation=False,
                        source_candidates=["data_coverage"],
                        fix="available_status_value_missing",
                    )
                )

    def _audit_sources(self, records: list[dict[str, Any]], data: dict[str, Any]) -> None:
        for index, source in enumerate(self._list(data.get("data_sources"))):
            name = str(source.get("name") or "")
            if name in {"CafeF", "Vietstock"}:
                records.append(
                    self._record(
                        "data_sources",
                        f"data_sources[{index}].name",
                        name,
                        raw=True,
                        normalized=False,
                        presentation=False,
                        source_candidates=["source_name", "source_type"],
                        fix="source_name_too_generic",
                    )
                )

    def _record(
        self,
        section: str,
        field: str,
        display_value: Any,
        *,
        raw: bool,
        normalized: bool,
        presentation: bool,
        source_candidates: list[str],
        fix: str,
    ) -> dict[str, Any]:
        return {
            "section": section,
            "field": field,
            "display_value": display_value if display_value not in (None, "") else "Chưa xác minh",
            "raw_data_available": raw,
            "normalized_data_available": normalized,
            "presentation_data_available": presentation,
            "source_candidates": source_candidates,
            "recommended_fix": fix,
        }

    def _card_by_label(self, section: dict[str, Any], label: str) -> dict[str, Any]:
        for card in section.get("cards") if isinstance(section.get("cards"), list) else []:
            if isinstance(card, dict) and card.get("label") == label:
                return card
        return {}

    def _is_missing(self, value: Any) -> bool:
        if value in MISSING_VALUES:
            return True
        return str(value).strip() in {"Chưa xác minh", "Chưa xác định"}

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list(self, value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def _scrub(self, value: Any) -> Any:
        return scrub_debug_payload(value)
