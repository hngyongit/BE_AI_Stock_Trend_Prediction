from __future__ import annotations

from analyse.constants.analysis_constants import DEFAULT_DISCLAIMER
from analyse.schemas.analysis_output_schema import (
    ActionPlan,
    DataQualityInfo,
    StockAnalysisData,
    StockAnalysisResponse,
    TrendInfo,
)
from analyse.schemas.stock_schema import StockAnalysisRequest
from analyse.services.data_normalizer_service import DataNormalizerService


class StockAnalysisService:
    """Service skeleton cho phan tich mot ma co phieu."""

    def __init__(self, normalizer: DataNormalizerService | None = None) -> None:
        self.normalizer = normalizer or DataNormalizerService()

    def build_placeholder_result(self, request: StockAnalysisRequest) -> dict:
        normalized = self.normalizer.normalize_stock_data(request.data.model_dump(by_alias=True))
        metadata = normalized["metadata"]
        response = StockAnalysisResponse(
            data=StockAnalysisData(
                symbol=request.symbol.upper(),
                summary=(
                    "Kết quả placeholder: module analyse đã nhận dữ liệu đầu vào. "
                    "Phân tích AI/LLM chi tiết sẽ được triển khai ở bước tiếp theo."
                ),
                dataQuality=DataQualityInfo(
                    level=metadata["qualityLevel"],
                    missingFields=metadata["missingFields"],
                    notes=metadata["notes"],
                ),
                trend=TrendInfo(
                    direction="UNCLEAR",
                    confidence=0.0,
                    reasoning=[
                        "Chưa gọi OpenAI và chưa có logic phân tích xu hướng trong skeleton."
                    ],
                ),
                strengths=[],
                risks=[],
                signals=[],
                actionPlan=ActionPlan(
                    watchPoints=[
                        "Kiểm tra lại latest_price, price_history và chất lượng dữ liệu crawler trước khi phân tích."
                    ],
                    riskManagement=[
                        "Không sử dụng kết quả placeholder như khuyến nghị giao dịch."
                    ],
                ),
                disclaimer=DEFAULT_DISCLAIMER,
            )
        )
        return response.model_dump()
