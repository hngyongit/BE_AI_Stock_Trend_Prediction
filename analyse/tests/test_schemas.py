from analyse.schemas.stock_schema import StockAnalysisRequest
from analyse.schemas.watchlist_schema import WatchlistAnalysisRequest


def test_stock_request_schema_accepts_expected_shape():
    payload = {
        "symbol": "VCB",
        "data": {
            "stock": {},
            "latestPrice": {},
            "priceHistory": [],
            "marketOverview": {},
            "financials": {},
            "crawlQuality": {},
        },
        "options": {
            "language": "vi",
            "riskProfile": "medium",
            "timeHorizon": "short_term",
        },
    }

    request = StockAnalysisRequest.model_validate(payload)

    assert request.symbol == "VCB"
    assert request.options.risk_profile == "medium"


def test_watchlist_request_schema_accepts_defaults():
    request = WatchlistAnalysisRequest.model_validate({"stocks": [{"symbol": "FPT", "data": {}}]})

    assert request.stocks[0].symbol == "FPT"
    assert request.options.language == "vi"
