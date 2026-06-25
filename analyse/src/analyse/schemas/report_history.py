from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReportHistoryFilters(BaseModel):
    symbol: str | None = None
    exchange: str | None = None
    provider: str | None = None
    model: str | None = None
    from_date: datetime | None = Field(default=None, alias="fromDate")
    to_date: datetime | None = Field(default=None, alias="toDate")
    page: int = 1
    limit: int = 20

    model_config = ConfigDict(populate_by_name=True)


class ReportHistoryListItem(BaseModel):
    id: str
    report_id: str
    symbol: str
    exchange: str
    company: str | None = None
    provider: str
    model: str
    total_score: float | None = None
    risk_score: float | None = None
    data_confidence: float | None = None
    decision_label: str | None = None
    created_at: datetime


class ReportHistoryListData(BaseModel):
    items: list[ReportHistoryListItem]
    page: int
    limit: int
    total: int


class ReportHistoryDetailData(BaseModel):
    id: str
    report_id: str
    report_json: dict[str, Any]
