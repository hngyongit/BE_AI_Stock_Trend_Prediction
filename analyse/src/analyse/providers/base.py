from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from analyse.schemas.llm import LLMGenerateResult, LLMReportOutput


class BaseLLMProvider(ABC):
    provider_name: str
    model: str

    @abstractmethod
    async def generate_report_json(self, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> LLMGenerateResult:
        """Nhận context đã chuẩn hóa và trả về JSON đã parse/validate sơ bộ."""
        raise NotImplementedError


def normalize_llm_report_output(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce provider JSON into the shared narrative-only LLM output schema."""
    source = raw.get("summary") if isinstance(raw.get("summary"), dict) else raw
    action_plan = _first(source, "action_plan", "actionPlan", "monitoring_plan", "monitoringPlan")
    action_plan = _normalize_action_plan(action_plan)
    scenarios = _first(source, "scenarios", "scenario_matrix", "scenarioMatrix")
    if isinstance(scenarios, dict):
        scenarios = [
            {**value, "name": key}
            if isinstance(value, dict)
            else {"name": key, "condition": str(value)}
            for key, value in scenarios.items()
            if value not in (None, "", {}, [])
        ]
    elif not isinstance(scenarios, list):
        scenarios = []
    checklist = _first(source, "checklist", "watch_points", "watchPoints")
    if isinstance(checklist, list):
        checklist = [
            item
            if isinstance(item, dict)
            else {"label": str(item), "note": str(item), "status": "pending"}
            for item in checklist
            if item not in (None, "", {}, [])
        ]
    else:
        checklist = []
    output = {
        "strengths": source.get("strengths", []),
        "weaknesses": source.get("weaknesses", []),
        "system_decision": source.get("system_decision", {}),
        "markdown_report": raw.get("markdown_report") or source.get("markdown_report", {}),
        "data_quality_notes": raw.get("data_quality_notes") or source.get("data_quality_notes", []),
        "executive_forecast": source.get("executive_forecast") or source.get("executiveForecast") or {},
        "quantitative_signal_summary": source.get("quantitative_signal_summary") or source.get("quantitativeSignalSummary") or {},
        "action_plan": action_plan,
        "scenarios": scenarios,
        "risk_map": source.get("risk_map") or source.get("riskMap") or [],
        "checklist": checklist,
        "evidence_table": source.get("evidence_table") or source.get("evidenceTable") or [],
    }
    return LLMReportOutput.model_validate(output).model_dump()


def _first(source: dict[str, Any], *keys: str) -> Any:
    if not isinstance(source, dict):
        return None
    for key in keys:
        value = source.get(key)
        if value not in (None, "", {}, []):
            return value
    return None


def _normalize_action_plan(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return {"short_term": [_normalize_action_item(item) for item in value]}
    if not isinstance(value, dict):
        return {}
    return {
        "short_term": [_normalize_action_item(item) for item in _as_list(value.get("short_term") or value.get("shortTerm"))],
        "medium_term": [_normalize_action_item(item) for item in _as_list(value.get("medium_term") or value.get("mediumTerm"))],
        "watch_points": [_normalize_action_item(item) for item in _as_list(value.get("watch_points") or value.get("watchPoints"))],
        "risk_management": [_normalize_action_item(item) for item in _as_list(value.get("risk_management") or value.get("riskManagement"))],
    }


def _normalize_action_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            "action": item.get("action") or item.get("task") or item.get("note") or item.get("content") or "",
            "condition": item.get("condition") or item.get("trigger") or item.get("signal") or "",
            "price_zone": item.get("price_zone") if "price_zone" in item else item.get("priceZone"),
            "price_zone_note": item.get("price_zone_note") or item.get("priceZoneNote") or "",
            "position_size_note": item.get("position_size_note") or item.get("positionSizeNote") or item.get("position_size") or item.get("positionSize") or "",
            "risk_note": item.get("risk_note") or item.get("riskNote") or item.get("risk") or item.get("guardrail") or item.get("note") or "",
            "source_basis": item.get("source_basis") or item.get("sourceBasis") or item.get("source") or "Dữ liệu hiện có",
        }
    text = str(item).strip() if item not in (None, "") else ""
    return {
        "action": text,
        "condition": "",
        "price_zone": None,
        "price_zone_note": "",
        "position_size_note": "",
        "risk_note": "",
        "source_basis": "Dữ liệu hiện có",
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}, []):
        return []
    return [value]
