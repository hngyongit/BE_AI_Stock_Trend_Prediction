from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from analyse.schemas.common import ProviderName, SourceStatus


class LLMReportPayload(BaseModel):
    provider: ProviderName
    symbol: str
    context: dict[str, Any]
    response_schema: dict[str, Any] = Field(default_factory=dict)


class LLMGenerateResult(BaseModel):
    provider: ProviderName
    model: str
    status: SourceStatus = "not_implemented"
    latency_ms: int = 0
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
