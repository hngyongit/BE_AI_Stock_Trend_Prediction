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

    def extract_company(self, stock_detail: dict[str, Any]) -> str | None:
        stock = stock_detail.get("stock") if isinstance(stock_detail.get("stock"), dict) else stock_detail
        return stock.get("company") or stock.get("company_name") or stock.get("name") or stock.get("organName")
