from __future__ import annotations

from fastapi import APIRouter

from analyse.api import controllers
from analyse.schemas.stock_schema import StockAnalysisRequest, StockFetchAnalysisRequest
from analyse.schemas.watchlist_schema import WatchlistAnalysisRequest

router = APIRouter(prefix="/api/analyse", tags=["analyse"])


@router.get("/health")
async def health() -> dict:
    return await controllers.health_controller()


@router.post("/stock")
async def analyse_stock(payload: StockAnalysisRequest) -> dict:
    # TODO: Sau nay route nay se nhan du lieu truc tiep tu client va goi LLM.
    return await controllers.stock_analysis_controller(payload)


@router.post("/watchlist")
async def analyse_watchlist(payload: WatchlistAnalysisRequest) -> dict:
    # TODO: Sau nay route nay se tong hop danh sach theo doi va goi LLM.
    return await controllers.watchlist_analysis_controller(payload)


@router.post("/fetch-and-analyse/stock")
async def fetch_and_analyse_stock(payload: StockFetchAnalysisRequest) -> dict:
    # TODO: Sau nay route nay se goi backend API roi moi chuan hoa va phan tich.
    return await controllers.fetch_and_analyse_stock_controller(payload)
