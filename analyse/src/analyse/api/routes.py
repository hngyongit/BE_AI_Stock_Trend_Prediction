from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from analyse.api.dependencies import get_report_service
from analyse.config.settings import get_settings
from analyse.schemas.common import api_success
from analyse.schemas.report import AnalyseOneReportRequest
from analyse.schemas.stock import StockAnalysisRequest, StockFetchAnalysisRequest
from analyse.schemas.watchlist import WatchlistAnalysisRequest
from analyse.services.config_diagnostic_service import ConfigDiagnosticService
from analyse.services.report_service import ReportService
from analyse.utils.auth import get_bearer_token_from_request

router = APIRouter(tags=["analyse"])


@router.get("/api/analyse/health")
async def health() -> dict:
    return api_success("Analyse service đã sẵn sàng.")


@router.get("/api/analyse/config-check")
async def config_check(check_backend: bool = Query(default=False, alias="checkBackend")) -> dict:
    service = ConfigDiagnosticService(get_settings())
    data = await service.build(check_backend=check_backend)
    return api_success("Kiểm tra cấu hình analyse hoàn tất.", data=data)


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
async def analyse_one_report(
    payload: AnalyseOneReportRequest,
    request: Request,
    service: ReportService = Depends(get_report_service),
) -> dict:
    user_token = get_bearer_token_from_request(request)
    result = await service.analyse_one_report(payload, user_token=user_token)
    status_code = int(result.get("code", 200)) if isinstance(result, dict) else 200
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=result)
    return result
