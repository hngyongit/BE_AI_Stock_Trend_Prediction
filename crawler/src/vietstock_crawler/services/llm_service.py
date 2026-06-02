from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from vietstock_crawler.config.settings import Settings, get_settings


@dataclass
class LLMReviewResult:
    enabled: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class LLMService:
    """Optional LLM extension point.

    The crawler does not depend on this service by default. It is intentionally
    designed for future tasks such as explaining crawl errors, reviewing
    suspicious parser outputs, generating plain-language stock summaries, or
    detecting abnormal values.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enable_llm and self.settings.openai_api_key)

    def review_suspicious_values(self, record: Dict[str, Any]) -> LLMReviewResult:
        if not self.enabled:
            return LLMReviewResult(False, "LLM disabled by configuration.")
        # Future implementation: call an LLM provider with a compact, redacted payload.
        return LLMReviewResult(True, "LLM review hook is configured but not implemented yet.", {"symbol": record.get("symbol")})

    def explain_crawl_error(self, symbol: str, error: str) -> LLMReviewResult:
        if not self.enabled:
            return LLMReviewResult(False, "LLM disabled by configuration.")
        return LLMReviewResult(True, "LLM error explanation hook is configured but not implemented yet.", {"symbol": symbol, "error": error})
