from __future__ import annotations

from fastapi import APIRouter, Depends

from analyse.api.dependencies import get_report_service
from analyse.schemas.common import api_success
from analyse.schemas.report import AnalyseOneReportRequest
from analyse.schemas.stock import StockAnalysisRequest, StockFetchAnalysisRequest
from analyse.schemas.watchlist import WatchlistAnalysisRequest
from analyse.services.report_service import ReportService

router = APIRouter(tags=["analyse"])


@router.get("/api/analyse/health")
async def health() -> dict:
    return api_success("Analyse service đã sẵn sàng.")


@router.post("/api/analyse/stock")
async def analyse_stock(payload: StockAnalysisRequest, service: ReportService = Depends(get_report_service)) -> dict:
    return service.build_direct_stock_placeholder(payload)


@router.post("/api/analyse/watchlist")
async def analyse_watchlist(payload: WatchlistAnalysisRequest, service: ReportService = Depends(get_report_service)) -> dict:
    return service.build_watchlist_placeholder(payload)


@router.post("/api/analyse/fetch-and-analyse/stock")
async def fetch_and_analyse_stock(payload: StockFetchAnalysisRequest, service: ReportService = Depends(get_report_service)) -> dict:
    return await service.fetch_and_analyse_stock_placeholder(payload)


@router.post("/api/ai-reports/analyse-one")
async def analyse_one_report(payload: AnalyseOneReportRequest, service: ReportService = Depends(get_report_service)) -> dict:
    return await service.analyse_one_report(payload)
