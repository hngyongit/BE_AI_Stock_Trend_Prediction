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
    output = {
        "strengths": source.get("strengths", []),
        "weaknesses": source.get("weaknesses", []),
        "system_decision": source.get("system_decision", {}),
        "markdown_report": raw.get("markdown_report") or source.get("markdown_report", {}),
        "data_quality_notes": raw.get("data_quality_notes") or source.get("data_quality_notes", []),
    }
    return LLMReportOutput.model_validate(output).model_dump()
