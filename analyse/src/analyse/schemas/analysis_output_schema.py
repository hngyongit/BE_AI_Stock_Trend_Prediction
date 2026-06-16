from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DataQualityInfo(BaseModel):
    level: Literal["GOOD", "MEDIUM", "LOW"] = "MEDIUM"
    missingFields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TrendInfo(BaseModel):
    direction: Literal["UP", "DOWN", "SIDEWAYS", "UNCLEAR"] = "UNCLEAR"
    confidence: float = 0.0
    reasoning: list[str] = Field(default_factory=list)


class ActionPlan(BaseModel):
    shortTerm: list[str] = Field(default_factory=list)
    mediumTerm: list[str] = Field(default_factory=list)
    watchPoints: list[str] = Field(default_factory=list)
    riskManagement: list[str] = Field(default_factory=list)


class StockAnalysisData(BaseModel):
    symbol: str
    summary: str
    dataQuality: DataQualityInfo = Field(default_factory=DataQualityInfo)
    trend: TrendInfo = Field(default_factory=TrendInfo)
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    actionPlan: ActionPlan = Field(default_factory=ActionPlan)
    disclaimer: str


class StockAnalysisResponse(BaseModel):
    success: bool = True
    data: StockAnalysisData


class WatchlistRankingItem(BaseModel):
    symbol: str
    opportunityLevel: Literal["HIGH", "MEDIUM", "LOW", "UNCLEAR"] = "UNCLEAR"
    riskLevel: Literal["HIGH", "MEDIUM", "LOW", "UNCLEAR"] = "UNCLEAR"
    notes: list[str] = Field(default_factory=list)


class WatchlistAnalysisData(BaseModel):
    summary: str
    ranking: list[WatchlistRankingItem] = Field(default_factory=list)
    attentionNeeded: list[str] = Field(default_factory=list)
    monitoringPlan: list[str] = Field(default_factory=list)
    keyMarketRisks: list[str] = Field(default_factory=list)
    dataQualityNotes: list[str] = Field(default_factory=list)
    disclaimer: str


class WatchlistAnalysisResponse(BaseModel):
    success: bool = True
    data: WatchlistAnalysisData


class ErrorInfo(BaseModel):
    code: str
    details: list[Any] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error: ErrorInfo | None = None
