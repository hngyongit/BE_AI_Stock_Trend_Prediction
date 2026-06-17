from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RiskProfile = Literal["low", "medium", "high"]
TimeHorizon = Literal["short_term", "medium_term", "long_term"]


class AnalysisOptions(BaseModel):
    language: str = "vi"
    risk_profile: RiskProfile = Field(default="medium", alias="riskProfile")
    time_horizon: TimeHorizon = Field(default="medium_term", alias="timeHorizon")

    model_config = ConfigDict(populate_by_name=True)


class StockDataBundle(BaseModel):
    stock: dict[str, Any] = Field(default_factory=dict)
    latest_price: dict[str, Any] = Field(default_factory=dict, alias="latestPrice")
    price_history: list[dict[str, Any]] = Field(default_factory=list, alias="priceHistory")
    market_overview: dict[str, Any] = Field(default_factory=dict, alias="marketOverview")
    financials: dict[str, Any] = Field(default_factory=dict)
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
