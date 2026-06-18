from __future__ import annotations

from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.providers.base import BaseLLMProvider
from analyse.schemas.llm import LLMGenerateResult


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.gemini_model

    async def generate_report_json(self, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> LLMGenerateResult:
        # TODO: Tích hợp Gemini SDK/HTTP thật ở bước production.
        return LLMGenerateResult(
            provider="gemini",
            model=self.model,
            status="not_implemented",
            data={"note": "GeminiProvider mới là placeholder; chưa gọi Gemini API thật.", "payload_symbol": payload.get("symbol")},
            warnings=["GeminiProvider chưa triển khai gọi model thật."],
        )
