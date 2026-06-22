from __future__ import annotations

import asyncio
import importlib
from time import perf_counter
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.prompts.report_prompts import build_report_prompt
from analyse.providers.base import BaseLLMProvider, normalize_llm_report_output
from analyse.schemas.llm import LLMGenerateResult
from analyse.utils.safe_json import safe_json_loads


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(self, settings: Settings | None = None, model: str | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = model or self.settings.gemini_model
        self._client = client

    async def generate_report_json(self, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> LLMGenerateResult:
        if not self.settings.gemini_enabled:
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="disabled",
                warnings=["Gemini provider đang bị tắt bởi GEMINI_ENABLED=false."],
            )

        if not self.settings.gemini_api_key and self._client is None:
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="failed",
                warnings=["Thiếu cấu hình GEMINI_API_KEY."],
            )

        started_at = perf_counter()
        timeout_seconds = max(int(self.settings.gemini_timeout_ms / 1000), 1)
        try:
            raw_response = await asyncio.wait_for(
                asyncio.to_thread(self._call_gemini_sync, payload, schema),
                timeout=timeout_seconds,
            )
            parsed = safe_json_loads(self._extract_response_text(raw_response))
            data = normalize_llm_report_output(parsed)
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="success",
                latency_ms=int((perf_counter() - started_at) * 1000),
                data=data,
                warnings=[],
            )
        except asyncio.TimeoutError:
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="failed",
                latency_ms=int((perf_counter() - started_at) * 1000),
                warnings=["LLM_UNAVAILABLE: Gemini timeout khi tạo structured output."],
            )
        except ImportError:
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="failed",
                latency_ms=int((perf_counter() - started_at) * 1000),
                warnings=["Thiếu dependency google-genai."],
            )
        except Exception as exc:  # pragma: no cover - lỗi runtime phụ thuộc provider bên ngoài
            return LLMGenerateResult(
                provider="gemini",
                model=self.model,
                status="failed",
                latency_ms=int((perf_counter() - started_at) * 1000),
                warnings=[f"LLM_UNAVAILABLE: Gemini error: {type(exc).__name__}."],
            )

    def _call_gemini_sync(self, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> Any:
        prompt = build_report_prompt(context=payload, schema=schema)
        client = self._get_client()
        config = self._build_config(schema)
        return client.models.generate_content(model=self.model, contents=prompt, config=config)

    def _get_client(self) -> Any:
        if self._client is None:
            genai = importlib.import_module("google.genai")
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def _build_config(self, schema: dict[str, Any] | None = None) -> Any:
        genai_types = importlib.import_module("google.genai.types")
        config_kwargs: dict[str, Any] = {
            "temperature": self.settings.gemini_temperature,
            "top_p": self.settings.gemini_top_p,
            "max_output_tokens": self.settings.gemini_max_output_tokens,
        }
        if self.settings.gemini_json_mode:
            config_kwargs["response_mime_type"] = "application/json"
            if schema:
                config_kwargs["response_schema"] = schema
        return genai_types.GenerateContentConfig(**config_kwargs)

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

        raise ValueError("Gemini trả response rỗng hoặc không có JSON text.")
