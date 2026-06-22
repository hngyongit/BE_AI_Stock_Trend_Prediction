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

    def normalize_analysis_data(self, payload: Any) -> dict[str, Any]:
        data = self.normalize_stock_detail(payload)
        latest_market = self._first_dict(data, "latest_market", "latestMarket", "latest_price", "latestPrice")
        price_history = self._first_list(data, "price_history", "priceHistory", "prices", "chart", "candles")
        financials_raw = data.get("financials") or {}
        financial_periods: list[dict[str, Any]] = []
        if isinstance(financials_raw, dict):
            financial_periods = self._first_list(financials_raw, "periods", "items")
        elif isinstance(financials_raw, list):
            financial_periods = [item for item in financials_raw if isinstance(item, dict)]

        financials = dict(financials_raw) if isinstance(financials_raw, dict) else {}
        financials["periods"] = financial_periods

        data_quality = self._normalize_data_quality(self._first_dict(data, "data_quality", "dataQuality"), financials, price_history)
        source_statuses = data.get("source_statuses") or data.get("sourceStatuses") or []
        if not isinstance(source_statuses, list):
            source_statuses = []
        source_success = data.get("_source_success") or data.get("source_success") or data.get("sourceSuccess") or {}
        if not isinstance(source_success, dict):
            source_success = {}

        return {
            "symbol": data.get("symbol") or self._nested_value(data, "stock", "symbol"),
            "exchange": data.get("exchange") or data.get("scope_exchange") or data.get("market_code") or self._nested_value(data, "stock", "market_code"),
            "company": data.get("company") or data.get("company_name") or data.get("name") or data.get("organName") or self.extract_company(data),
            "latest_market": latest_market,
            "latest_price": latest_market,
            "price_history": price_history,
            "priceHistory": price_history,
            "financials": financials,
            "financial_balance": self._first_dict(data, "financial_balance", "financialBalance"),
            "hose_market_context": self._first_dict(data, "hose_market_context", "hoseMarketContext", "market_overview", "marketOverview"),
            "market_general_context": self._first_dict(data, "market_general_context", "marketGeneralContext"),
            "industry_peer_context": self._first_dict(data, "industry_peer_context", "industryPeerContext"),
            "same_industry_recommendation": self._first_dict(data, "same_industry_recommendation", "sameIndustryRecommendation"),
            "data_quality": data_quality,
            "source_statuses": source_statuses,
            "_source_success": source_success,
            "raw": data,
        }

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

    def _normalize_data_quality(
        self,
        data_quality: dict[str, Any],
        financials: dict[str, Any],
        price_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        periods = financials.get("periods") if isinstance(financials.get("periods"), list) else []
        missing_fields = data_quality.get("missing_fields") or data_quality.get("missingFields") or []
        warnings = data_quality.get("warnings") or []
        return {
            "financials_loaded": self._bool_value(data_quality, "financials_loaded", "financialsLoaded", fallback=bool(periods)),
            "financial_periods_count": self._int_value(data_quality, "financial_periods_count", "financialPeriodsCount", fallback=len(periods)),
            "price_history_points": self._int_value(data_quality, "price_history_points", "priceHistoryPoints", fallback=len(price_history)),
            "market_context_loaded": self._bool_value(data_quality, "market_context_loaded", "marketContextLoaded", fallback=False),
            "peer_context_loaded": self._bool_value(data_quality, "peer_context_loaded", "peerContextLoaded", fallback=False),
            "missing_fields": missing_fields if isinstance(missing_fields, list) else [],
            "warnings": warnings if isinstance(warnings, list) else [],
            "units": data_quality.get("units") if isinstance(data_quality.get("units"), dict) else {},
        }

    def _first_dict(self, data: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                return value
        return {}

    def _first_list(self, data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _nested_value(self, data: dict[str, Any], parent: str, key: str) -> Any:
        parent_value = data.get(parent)
        if isinstance(parent_value, dict):
            return parent_value.get(key)
        return None

    def _bool_value(self, data: dict[str, Any], *keys: str, fallback: bool = False) -> bool:
        for key in keys:
            value = data.get(key)
            if isinstance(value, bool):
                return value
        return fallback

    def _int_value(self, data: dict[str, Any], *keys: str, fallback: int = 0) -> int:
        for key in keys:
            value = data.get(key)
            if isinstance(value, int):
                return value
        return fallback
