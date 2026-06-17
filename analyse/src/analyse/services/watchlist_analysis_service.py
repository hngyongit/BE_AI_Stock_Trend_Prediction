from __future__ import annotations

from analyse.constants.analysis_constants import DEFAULT_DISCLAIMER
from analyse.schemas.analysis_output_schema import (
    WatchlistAnalysisData,
    WatchlistAnalysisResponse,
    WatchlistRankingItem,
)
from analyse.schemas.watchlist_schema import WatchlistAnalysisRequest
from analyse.services.data_normalizer_service import DataNormalizerService


class WatchlistAnalysisService:
    """Service skeleton cho phan tich watchlist."""

    def __init__(self, normalizer: DataNormalizerService | None = None) -> None:
        self.normalizer = normalizer or DataNormalizerService()

    def build_placeholder_result(self, request: WatchlistAnalysisRequest) -> dict:
        normalized = self.normalizer.normalize_watchlist_data(
            [item.model_dump() for item in request.stocks]
        )
        symbols = [item.symbol.upper() for item in request.stocks]
        response = WatchlistAnalysisResponse(
            data=WatchlistAnalysisData(
                summary=(
                    "Kết quả placeholder: analyse service đã nhận watchlist. "
                    "Xếp hạng rủi ro/cơ hội bằng AI sẽ được triển khai sau."
                ),
                ranking=[WatchlistRankingItem(symbol=symbol) for symbol in symbols],
                attentionNeeded=[],
                monitoringPlan=[
                    "Theo dõi chất lượng dữ liệu, giá mới nhất và lịch sử OHLCV trước khi tạo nhận định."
                ],
                keyMarketRisks=[],
                dataQualityNotes=normalized["metadata"]["notes"],
                disclaimer=DEFAULT_DISCLAIMER,
            )
        )
        return response.model_dump()
