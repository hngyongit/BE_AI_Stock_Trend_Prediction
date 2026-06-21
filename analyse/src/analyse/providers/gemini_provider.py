from __future__ import annotations

import asyncio
import importlib
import time
from typing import Any

from pydantic import BaseModel, Field

from analyse.config.settings import Settings, get_settings
from analyse.prompts.report_prompts import build_report_prompt
from analyse.providers.base import BaseLLMProvider
from analyse.schemas.llm import LLMGenerateResult
from analyse.utils.safe_json import safe_json_loads


class GeminiProviderError(RuntimeError):
    """Custom provider error để chuẩn hóa lỗi LLM tầng Gemini."""

    error_type = "LLM_UNAVAILABLE"


class GeminiStructuredResponse(BaseModel):
    summary: dict[str, Any] = Field(default_factory=dict)
    market_overview: dict[str, Any] = Field(default_factory=dict)
    narrative: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


DEFAULT_STRUCTURED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "object"},
        "market_overview": {"type": "object"},
        "narrative": {"type": "object"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary"],
    "additionalProperties": True,
}


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.gemini_model

    async def generate_report_json(self, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> LLMGenerateResult:
        started_at = time.perf_counter()
        timeout_seconds = max(int(self.settings.gemini_timeout_ms / 1000), 1)
        payload_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

        try:
            raw_response = await asyncio.wait_for(
                asyncio.to_thread(self._call_gemini_sync, payload, schema or DEFAULT_STRUCTURED_SCHEMA),
                timeout=timeout_seconds,
            )
            structured_output = self._parse_structured_response(raw_response)
            output_data = self._overwrite_quantitative_fields(payload, structured_output.model_dump())
            latency_ms = int((time.perf_counter() - started_at) * 1000)

            warnings = structured_output.warnings or [
                "Đã áp dụng cơ chế anti-hallucination: giữ nguyên số liệu định lượng từ payload gốc."
            ]

            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="success",
                latency_ms=latency_ms,
                data=output_data,
                warnings=warnings,
            )
        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="failed",
                latency_ms=latency_ms,
                data={"summary": payload_summary},
                warnings=["LLM_UNAVAILABLE: Gemini timeout khi tạo structured output."],
            )
        except GeminiProviderError as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="failed",
                latency_ms=latency_ms,
                data={"summary": payload_summary},
                warnings=[f"{exc.error_type}: {exc}"],
            )
        except Exception as exc:  # pragma: no cover - lỗi runtime phụ thuộc provider
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="failed",
                latency_ms=latency_ms,
                data={"summary": payload_summary},
                warnings=[f"LLM_UNAVAILABLE: Gemini unexpected error: {exc}"],
            )

    def _call_gemini_sync(self, payload: dict[str, Any], schema: dict[str, Any]) -> Any:
        if not self.settings.gemini_enabled:
            raise GeminiProviderError("Gemini provider đang bị tắt bởi cấu hình GEMINI_ENABLED=false.")
        if not self.settings.gemini_api_key:
            raise GeminiProviderError("Thiếu GEMINI_API_KEY.")

        try:
            genai = importlib.import_module("google.genai")
            genai_types = importlib.import_module("google.genai.types")
        except ImportError as exc:  # pragma: no cover
            raise GeminiProviderError("Thiếu dependency google-genai.") from exc

        client = genai.Client(api_key=self.settings.gemini_api_key)
        prompt = build_report_prompt(payload)
        config = genai_types.GenerateContentConfig(
            temperature=0.2,
            top_p=self.settings.gemini_top_p,
            max_output_tokens=self.settings.gemini_max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema,
        )

        try:
            return client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:  # pragma: no cover
            raise GeminiProviderError(f"Gemini API error: {exc}") from exc

    def _parse_structured_response(self, response: Any) -> GeminiStructuredResponse:
        response_text = self._extract_response_text(response)
        parsed = safe_json_loads(response_text)

        if "summary" not in parsed and isinstance(parsed, dict):
            parsed = {"summary": parsed}

        return GeminiStructuredResponse.model_validate(parsed)

    def _extract_response_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text

        candidates = getattr(response, "candidates", None)
        if isinstance(candidates, list):
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None)
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    part_text = getattr(part, "text", None)
                    if isinstance(part_text, str) and part_text.strip():
                        return part_text

        raise GeminiProviderError("Gemini trả response rỗng hoặc không có JSON text.")

    def _overwrite_quantitative_fields(self, payload: dict[str, Any], llm_data: dict[str, Any]) -> dict[str, Any]:
        payload_summary = payload.get("summary")
        if not isinstance(payload_summary, dict):
            return llm_data

        summary = llm_data.get("summary") if isinstance(llm_data.get("summary"), dict) else {}

        hard_fields = (
            "symbol",
            "company",
            "scope_exchange",
            "disclaimer",
            "data_coverage",
            "latest_market",
            "momentum",
            "bctc_3q",
            "financial_balance",
            "hose_market_context",
            "scores",
            "system_decision",
            "warnings",
        )
        for field in hard_fields:
            if field in payload_summary:
                summary[field] = payload_summary[field]

        plan = summary.get("investment_plan") if isinstance(summary.get("investment_plan"), dict) else {}
        payload_plan = payload_summary.get("investment_plan")
        if isinstance(payload_plan, dict):
            for field in ("reference_levels", "position_sizing", "action_table", "decision"):
                if field in payload_plan:
                    plan[field] = payload_plan[field]
        summary["investment_plan"] = plan

        llm_data["summary"] = summary
        return llm_data
