from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from analyse.api.dependencies import get_ai_report_history_service, get_report_service, get_user_identity_service
from analyse.config.settings import get_settings
from analyse.schemas.common import api_error, api_success
from analyse.schemas.report import AnalyseOneReportRequest
from analyse.schemas.report_history import ReportHistoryFilters
from analyse.schemas.stock import StockAnalysisRequest, StockFetchAnalysisRequest
from analyse.schemas.watchlist import WatchlistAnalysisRequest
from analyse.services.ai_report_history_service import (
    AiReportHistoryDisabledError,
    AiReportHistoryNotFoundError,
    AiReportHistoryService,
    AiReportHistoryUnavailableError,
)
from analyse.services.config_diagnostic_service import ConfigDiagnosticService
from analyse.services.report_service import ReportService
from analyse.services.user_identity_service import UserIdentityMalformedError, UserIdentityService, UserIdentityUnauthorizedError
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


@router.post("/api/analyse/stock", include_in_schema=False)
async def analyse_stock(payload: StockAnalysisRequest) -> JSONResponse:
    _ = payload
    return _not_implemented_response("Endpoint legacy /api/analyse/stock chưa được triển khai. Vui lòng dùng /api/ai-reports/analyse-one.")


@router.post("/api/analyse/watchlist", include_in_schema=False)
async def analyse_watchlist(payload: WatchlistAnalysisRequest) -> JSONResponse:
    _ = payload
    return _not_implemented_response("Endpoint legacy /api/analyse/watchlist chưa được triển khai. Vui lòng dùng /api/ai-reports/analyse-one.")


@router.post("/api/analyse/fetch-and-analyse/stock", include_in_schema=False)
async def fetch_and_analyse_stock(payload: StockFetchAnalysisRequest) -> JSONResponse:
    _ = payload
    return _not_implemented_response(
        "Endpoint legacy /api/analyse/fetch-and-analyse/stock chưa được triển khai. Vui lòng dùng /api/ai-reports/analyse-one."
    )


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


@router.get("/api/ai-reports/history")
async def list_report_history(
    request: Request,
    symbol: str | None = Query(default=None),
    exchange: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None, alias="fromDate"),
    to_date: datetime | None = Query(default=None, alias="toDate"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    identity_service: UserIdentityService = Depends(get_user_identity_service),
    history_service: AiReportHistoryService = Depends(get_ai_report_history_service),
):
    user_token = get_bearer_token_from_request(request)
    current_user = await _resolve_current_user(user_token, identity_service)
    if isinstance(current_user, JSONResponse):
        return current_user
    filters = ReportHistoryFilters(
        symbol=symbol,
        exchange=exchange,
        provider=provider,
        model=model,
        fromDate=from_date,
        toDate=to_date,
        page=page,
        limit=limit,
    )
    try:
        data = await history_service.list_history(current_user=current_user, filters=filters)
    except AiReportHistoryDisabledError:
        return _error_response(503, "Tính năng lịch sử báo cáo AI chưa được bật.", "HISTORY_DISABLED")
    except AiReportHistoryUnavailableError:
        return _error_response(503, "Không đọc được lịch sử báo cáo AI trong lần này.", "HISTORY_UNAVAILABLE")
    return api_success("Lấy lịch sử báo cáo AI thành công.", data=data.model_dump())


@router.get("/api/ai-reports/history/{history_id}")
async def get_report_history_detail(
    history_id: str,
    request: Request,
    identity_service: UserIdentityService = Depends(get_user_identity_service),
    history_service: AiReportHistoryService = Depends(get_ai_report_history_service),
):
    user_token = get_bearer_token_from_request(request)
    current_user = await _resolve_current_user(user_token, identity_service)
    if isinstance(current_user, JSONResponse):
        return current_user
    try:
        data = await history_service.get_history_detail(current_user=current_user, history_id=history_id)
    except AiReportHistoryDisabledError:
        return _error_response(503, "Tính năng lịch sử báo cáo AI chưa được bật.", "HISTORY_DISABLED")
    except AiReportHistoryNotFoundError:
        return _error_response(404, "Không tìm thấy báo cáo trong lịch sử của người dùng hiện tại.", "HISTORY_NOT_FOUND")
    except AiReportHistoryUnavailableError:
        return _error_response(503, "Không đọc được chi tiết lịch sử báo cáo AI trong lần này.", "HISTORY_UNAVAILABLE")
    return api_success("Lấy chi tiết lịch sử báo cáo AI thành công.", data=data.model_dump())


@router.delete("/api/ai-reports/history/{history_id}")
async def delete_report_history(
    history_id: str,
    request: Request,
    identity_service: UserIdentityService = Depends(get_user_identity_service),
    history_service: AiReportHistoryService = Depends(get_ai_report_history_service),
):
    user_token = get_bearer_token_from_request(request)
    current_user = await _resolve_current_user(user_token, identity_service)
    if isinstance(current_user, JSONResponse):
        return current_user
    try:
        await history_service.delete_history(current_user=current_user, history_id=history_id)
    except AiReportHistoryDisabledError:
        return _error_response(503, "Tính năng lịch sử báo cáo AI chưa được bật.", "HISTORY_DISABLED")
    except AiReportHistoryNotFoundError:
        return _error_response(404, "Không tìm thấy báo cáo trong lịch sử của người dùng hiện tại.", "HISTORY_NOT_FOUND")
    except AiReportHistoryUnavailableError:
        return _error_response(503, "Không xóa được lịch sử báo cáo AI trong lần này.", "HISTORY_UNAVAILABLE")
    return api_success("Xóa lịch sử báo cáo AI thành công.", data={"deleted": True})


async def _resolve_current_user(user_token: str, identity_service: UserIdentityService):
    try:
        return await identity_service.resolve_current_user(user_token)
    except UserIdentityUnauthorizedError:
        return _error_response(401, "Phiên đăng nhập đã hết hạn hoặc token không hợp lệ.", "AUTH_INVALID")
    except UserIdentityMalformedError:
        return _error_response(502, "Không xác định được người dùng hiện tại từ Backend.", "CURRENT_USER_MALFORMED")
    except Exception:
        return _error_response(502, "Không xác thực được người dùng hiện tại từ Backend.", "CURRENT_USER_UNAVAILABLE")


def _error_response(status_code: int, message: str, error_type: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=api_error(message, error_type, code=status_code))


def _not_implemented_response(message: str) -> JSONResponse:
    return _error_response(501, message, "NOT_IMPLEMENTED")
