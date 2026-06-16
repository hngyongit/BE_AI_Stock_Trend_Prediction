from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from analyse.schemas.stock_schema import AnalysisOptions


class WatchlistStockItem(BaseModel):
    symbol: str
    data: dict[str, Any] = Field(default_factory=dict)


class WatchlistAnalysisRequest(BaseModel):
    user_id: str | None = Field(default=None, alias="userId")
    stocks: list[WatchlistStockItem] = Field(default_factory=list)
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)

    model_config = ConfigDict(populate_by_name=True)
