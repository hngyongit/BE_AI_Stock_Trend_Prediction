from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RiskProfile = Literal["low", "medium", "high"]
TimeHorizon = Literal["short", "medium", "long", "short_term", "medium_term", "long_term"]


class AnalysisOptions(BaseModel):
    language: str = "vi"
    risk_profile: RiskProfile = Field(default="medium", alias="riskProfile")
    time_horizon: TimeHorizon = Field(default="medium", alias="timeHorizon")
    include_external_research: bool = Field(default=True, alias="includeExternalResearch")
    render_markdown: bool = Field(default=True, alias="renderMarkdown")
    render_html: bool = Field(default=True, alias="renderHtml")
    capital_vnd: int | None = Field(default=None, alias="capitalVnd")
    risk_per_trade_pct: float | None = Field(default=None, alias="riskPerTradePct")
    max_position_pct: float | None = Field(default=None, alias="maxPositionPct")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class StockDataBundle(BaseModel):
    stock: dict[str, Any] = Field(default_factory=dict)
    latest_price: dict[str, Any] = Field(default_factory=dict, alias="latestPrice")
    price_history: list[dict[str, Any]] = Field(default_factory=list, alias="priceHistory")
    market_overview: dict[str, Any] = Field(default_factory=dict, alias="marketOverview")
    financials: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    crawl_quality: dict[str, Any] = Field(default_factory=dict, alias="crawlQuality")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class StockAnalysisRequest(BaseModel):
    symbol: str
    data: StockDataBundle
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


class StockFetchAnalysisRequest(BaseModel):
    symbol: str
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)
    fetch_from_backend: bool = Field(default=True, alias="fetchFromBackend")

    model_config = ConfigDict(populate_by_name=True)
