from __future__ import annotations

RISK_PROFILES = ("low", "medium", "high")
TIME_HORIZONS = ("short_term", "medium_term", "long_term")

DEFAULT_DISCLAIMER = (
    "Nội dung này chỉ là thông tin tham khảo và hỗ trợ ra quyết định, "
    "không phải khuyến nghị mua bán hay cam kết lợi nhuận."
)

BACKEND_ROUTE_NOTES = {
    "stock_list": "GET /api/stocks trả về { success, message, data: { items, pagination } }.",
    "stock_detail": "GET /api/stocks/:symbol trả về stock master và latest_price.",
    "stock_chart": "GET /api/stocks/:symbol/chart?range=1m trả về mảng OHLCV.",
    "watchlist": "GET /api/watchlists yêu cầu Bearer token và trả về items/limit/currentCount/overLimit.",
    "user_dashboard": "GET /api/dashboard/user yêu cầu Bearer token role USER và trả về watchlist, market_leaders, market_overview.",
    "unclear": (
        "Các module financials, crawl-logs, crawl-jobs, market-overview có file nhưng đang rỗng "
        "hoặc chưa được mount trong api/src/app.js."
    ),
}
