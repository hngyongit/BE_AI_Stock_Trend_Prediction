from __future__ import annotations

from typing import Any


class StockDataService:
    """Chuẩn hóa dữ liệu stock từ direct payload hoặc Backend API."""

    def unwrap_backend_response(self, payload: Any) -> Any:
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def normalize_stock_detail(self, payload: Any) -> dict[str, Any]:
        data = self.unwrap_backend_response(payload)
        if not isinstance(data, dict):
            data = {"raw": data}
        return data

    def normalize_stock_chart(self, payload: Any) -> list[dict[str, Any]]:
        data = self.unwrap_backend_response(payload)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("items", "prices", "chart", "candles", "price_history", "priceHistory"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def merge_chart_history(self, stock_detail: dict[str, Any], chart_payload: Any) -> dict[str, Any]:
        history = self.normalize_stock_chart(chart_payload)
        if not history:
            return stock_detail
        merged = dict(stock_detail)
        merged["price_history"] = history
        merged["priceHistory"] = history
        return merged

    def extract_company(self, stock_detail: dict[str, Any]) -> str | None:
        stock = stock_detail.get("stock") if isinstance(stock_detail.get("stock"), dict) else stock_detail
        return stock.get("company") or stock.get("company_name") or stock.get("name") or stock.get("organName")
