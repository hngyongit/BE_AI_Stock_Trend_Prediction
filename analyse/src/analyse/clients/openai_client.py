from __future__ import annotations

from typing import Any

from analyse.config.openai_config import OpenAIConfig, get_openai_config


class OpenAIAnalysisClient:
    """Skeleton client cho OpenAI; khong goi API that trong giai doan scaffold."""

    def __init__(self, config: OpenAIConfig | None = None) -> None:
        self.config = config or get_openai_config()

    @property
    def is_configured(self) -> bool:
        return self.config.is_configured

    async def generate_json_analysis(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        TODO: Tich hop OpenAI Python SDK va bat buoc model tra ve JSON hop le.

        Khong log API key, khong dua API key vao response, va can xu ly timeout
        cung loi JSON khong hop le trong giai doan production.
        """
        raise NotImplementedError("OpenAI analysis generation chua duoc trien khai.")
