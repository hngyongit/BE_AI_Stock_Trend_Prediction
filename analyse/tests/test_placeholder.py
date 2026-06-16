from analyse.schemas.stock_schema import StockAnalysisRequest
from analyse.services.stock_analysis_service import StockAnalysisService


def test_stock_analysis_placeholder_returns_success():
    request = StockAnalysisRequest.model_validate(
        {
            "symbol": "VCB",
            "data": {
                "stock": {},
                "latestPrice": {},
                "priceHistory": [],
                "marketOverview": {},
                "financials": {},
                "crawlQuality": {},
            },
        }
    )

    result = StockAnalysisService().build_placeholder_result(request)

    assert result["success"] is True
    assert result["data"]["symbol"] == "VCB"
    assert result["data"]["trend"]["direction"] == "UNCLEAR"
