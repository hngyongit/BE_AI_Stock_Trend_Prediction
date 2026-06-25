from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


EvidenceSourceType = Literal[
    "backend",
    "structured_financial",
    "company_profile",
    "market_data",
    "peer_data",
    "news",
    "official_disclosure",
    "model_inference",
]


class ExtractedFact(BaseModel):
    key: str
    label: str
    value: Any
    unit: str | None = None
    period: str | None = None
    confidence: float = 0.0
    source_name: str
    source_url: str | None = None


class SourceEvidence(BaseModel):
    source_name: str
    source_type: EvidenceSourceType
    url: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    crawled_at: datetime
    symbol: str
    exchange: str | None = None
    company_name: str | None = None
    summary: str
    extracted_facts: list[ExtractedFact] = Field(default_factory=list)
    relevance_score: float = 0.0
    reliability_score: float = 0.0
    freshness_score: float = 0.0
    usable: bool = True
    warnings: list[str] = Field(default_factory=list)
    inclusion_reason: str | None = None


class ForecastScenario(BaseModel):
    scenario: str
    probability_pct: int
    time_horizon: str
    condition: str
    expected_behavior: str
    supporting_signals: list[str] = Field(default_factory=list)
    invalidation_signals: list[str] = Field(default_factory=list)
    risk_note: str
    inference_basis: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    symbol: str
    exchange: str | None = None
    company_name: str | None = None
    generated_at: datetime
    sources_attempted: list[str] = Field(default_factory=list)
    sources_successful: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
    evidence_used: list[SourceEvidence] = Field(default_factory=list)
    evidence_rejected: list[SourceEvidence] = Field(default_factory=list)
    research_queries: list[str] = Field(default_factory=list)
    forecast_scenarios: list[ForecastScenario] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
