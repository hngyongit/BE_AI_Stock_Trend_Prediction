from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from analyse.schemas.llm import LLMGenerateResult


class BaseLLMProvider(ABC):
    provider_name: str
    model: str

    @abstractmethod
    async def generate_report_json(self, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> LLMGenerateResult:
        """Nhận context đã chuẩn hóa và trả về JSON đã parse/validate sơ bộ."""
        raise NotImplementedError
