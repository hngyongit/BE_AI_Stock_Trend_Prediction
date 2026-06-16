from __future__ import annotations

from analyse.schemas.stock_schema import StockAnalysisRequest, StockFetchAnalysisRequest
from analyse.schemas.watchlist_schema import WatchlistAnalysisRequest
from analyse.services.stock_analysis_service import StockAnalysisService
from analyse.services.watchlist_analysis_service import WatchlistAnalysisService
from analyse.utils.response_utils import success_response


async def health_controller() -> dict:
    return success_response(
        "Analyse service đã sẵn sàng. Logic phân tích AI/LLM sẽ được triển khai ở bước tiếp theo."
    )


async def stock_analysis_controller(payload: StockAnalysisRequest) -> dict:
    service = StockAnalysisService()
    return service.build_placeholder_result(payload)


async def watchlist_analysis_controller(payload: WatchlistAnalysisRequest) -> dict:
    service = WatchlistAnalysisService()
    return service.build_placeholder_result(payload)


async def fetch_and_analyse_stock_controller(payload: StockFetchAnalysisRequest) -> dict:
    return success_response(
        "Chế độ fetch-and-analyse đã được khai báo skeleton. Logic gọi backend API và OpenAI sẽ được triển khai sau.",
        data={
            "symbol": payload.symbol.upper(),
            "backendMode": "fetch",
            "status": "NOT_IMPLEMENTED",
        },
    )
