from __future__ import annotations

from pydantic import BaseModel, Field

from analyse.schemas.common import SourceStatus


class ResearchItem(BaseModel):
    source: str
    type: str
    title: str | None = None
    url: str | None = None
    published_at: str | None = None
    snippet: str | None = None
    tone: str | None = None
    relevance_score: float | None = None
    positive_flags: list[str] = Field(default_factory=list)
    negative_flags: list[str] = Field(default_factory=list)
    catalyst_flags: list[str] = Field(default_factory=list)
    status: SourceStatus = "success"


class ExternalResearchContext(BaseModel):
    enabled: bool = True
    status: SourceStatus = "disabled"
    items: list[ResearchItem] = Field(default_factory=list)
    flag_summary: dict = Field(default_factory=dict)
    source_statuses: list[dict] = Field(default_factory=list)
    note: str | None = None
