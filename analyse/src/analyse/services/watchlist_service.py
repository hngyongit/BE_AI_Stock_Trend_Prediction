from __future__ import annotations

from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.schemas.watchlist import WatchlistStockItem
from analyse.utils.symbol_utils import normalize_symbol, normalize_symbols


class WatchlistService:
    """Xử lý watchlist và rule chỉ phân tích 1 mã trong tối đa 5 mã."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def extract_symbols_from_backend_payload(self, payload: Any) -> list[str]:
        return [item["symbol"] for item in self.extract_items_from_backend_payload(payload)]

    def extract_items_from_backend_payload(self, payload: Any) -> list[dict[str, str | None]]:
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, dict):
            items = data.get("items") or data.get("watchlist") or data.get("stocks") or []
        else:
            items = data or []

        result: list[dict[str, str | None]] = []
        for item in items:
            if isinstance(item, str):
                symbol = item
                exchange = None
            elif isinstance(item, dict):
                symbol = self._extract_symbol(item)
                exchange = self._extract_exchange(item)
            else:
                continue
            clean_symbol = normalize_symbol(symbol)
            if clean_symbol:
                result.append({"symbol": clean_symbol, "exchange": self._normalize_exchange(exchange)})
        return result

    def limit_symbols(self, symbols: list[str]) -> list[str]:
        return symbols[: self.settings.max_watchlist_symbols]

    def limit_items(self, items: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
        return items[: self.settings.max_watchlist_symbols]

    def validate_symbol_allowed(
        self,
        requested_symbol: str,
        allowed_symbols: list[str],
        *,
        requested_exchange: str | None = None,
        allowed_items: list[dict[str, str | None]] | None = None,
    ) -> tuple[bool, str]:
        symbol = normalize_symbol(requested_symbol)
        exchange = self._normalize_exchange(requested_exchange)
        if allowed_items:
            for item in allowed_items:
                item_symbol = normalize_symbol(item.get("symbol"))
                item_exchange = self._normalize_exchange(item.get("exchange"))
                if item_symbol != symbol:
                    continue
                if item_exchange and exchange and item_exchange != exchange:
                    continue
                return True, symbol
            return False, symbol
        return symbol in set(allowed_symbols), symbol

    def build_placeholder_result(self, stocks: list[WatchlistStockItem]) -> dict[str, Any]:
        symbols = normalize_symbols([item.symbol for item in stocks])
        return {
            "summary": "Watchlist placeholder: service đã nhận danh sách mã, phân tích AI sẽ triển khai sau.",
            "allowed_symbols": self.limit_symbols(symbols),
            "total_symbols_received": len(symbols),
        }

    def _extract_symbol(self, item: dict[str, Any]) -> str | None:
        direct = item.get("symbol") or item.get("code") or item.get("stockSymbol") or item.get("stock_code")
        if direct:
            return str(direct)

        stock = item.get("stock") or item.get("stock_id")
        if isinstance(stock, dict):
            return stock.get("symbol") or stock.get("code") or stock.get("stockSymbol") or stock.get("stock_code")
        return None

    def _extract_exchange(self, item: dict[str, Any]) -> str | None:
        direct = item.get("exchange") or item.get("market_code") or item.get("marketCode") or item.get("scopeExchange")
        if direct:
            return str(direct)

        stock = item.get("stock") or item.get("stock_id")
        if isinstance(stock, dict):
            return stock.get("exchange") or stock.get("market_code") or stock.get("marketCode") or stock.get("scopeExchange")
        return None

    def _normalize_exchange(self, value: Any) -> str | None:
        clean = str(value or "").strip().upper()
        return clean or None
