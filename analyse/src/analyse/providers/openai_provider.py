from __future__ import annotations

import importlib
from time import perf_counter
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.prompts.report_prompts import build_report_prompt
from analyse.providers.base import BaseLLMProvider, normalize_llm_report_output
from analyse.schemas.llm import LLMGenerateResult, LLMReportOutput


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"

    def __init__(self, settings: Settings | None = None, model: str | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = model or self.settings.openai_model
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            openai_module = importlib.import_module("openai")
            self._client = openai_module.AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.openai_timeout_ms / 1000,
                max_retries=2,
            )
        return self._client

    async def generate_report_json(self, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> LLMGenerateResult:
        if not self.settings.openai_enabled:
            return LLMGenerateResult(
                provider="openai",
                model=self.model,
                status="disabled",
                warnings=["OpenAI provider đang bị tắt bởi OPENAI_ENABLED=false."],
            )

        if not self.settings.openai_api_key and self._client is None:
            return LLMGenerateResult(
                provider="openai",
                model=self.model,
                status="failed",
                warnings=["Thiếu cấu hình OPENAI_API_KEY."],
            )

        started_at = perf_counter()
        try:
            prompt = build_report_prompt(context=payload, schema=schema)
            client = self._get_client()
            response = await client.responses.parse(
                model=self.model,
                input=prompt,
                text_format=LLMReportOutput,
                max_output_tokens=self.settings.openai_max_output_tokens,
                temperature=self.settings.openai_temperature,
            )

            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                return LLMGenerateResult(
                    provider="openai",
                    model=self.model,
                    status="failed",
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    warnings=["OpenAI không trả về structured output."],
                )

            raw_data = parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)
            data = normalize_llm_report_output(raw_data)
            return LLMGenerateResult(
                provider="openai",
                model=self.model,
                status="success",
                latency_ms=int((perf_counter() - started_at) * 1000),
                data=data,
                warnings=[],
            )
        except ImportError:
            return LLMGenerateResult(
                provider="openai",
                model=self.model,
                status="failed",
                latency_ms=int((perf_counter() - started_at) * 1000),
                warnings=["Thiếu dependency openai."],
            )
        except Exception as exc:  # pragma: no cover - lỗi runtime phụ thuộc provider bên ngoài
            return LLMGenerateResult(
                provider="openai",
                model=self.model,
                status="failed",
                latency_ms=int((perf_counter() - started_at) * 1000),
                warnings=[f"Không thể tạo phân tích bằng OpenAI: {type(exc).__name__}."],
            )
