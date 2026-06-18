from __future__ import annotations

from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.providers.base import BaseLLMProvider
from analyse.schemas.llm import LLMGenerateResult


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.openai_model

    async def generate_report_json(self, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> LLMGenerateResult:
        # TODO: Tích hợp OpenAI SDK thật ở bước production.
        return LLMGenerateResult(
            provider="openai",
            model=self.model,
            status="not_implemented",
            data={"note": "OpenAIProvider mới là placeholder; chưa gọi OpenAI API thật.", "payload_symbol": payload.get("symbol")},
            warnings=["OpenAIProvider chưa triển khai gọi model thật."],
        )
