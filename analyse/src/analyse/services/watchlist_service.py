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

    def extract_items_from_backend_payload(self, payload: Any) -> list[dict[str, Any]]:
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, dict):
            items = data.get("items") or data.get("watchlist") or data.get("stocks") or []
        else:
            items = data or []

        result: list[dict[str, Any]] = []
        for item in items:
            raw_item: Any = item
            watchlist_id = None
            stock_id = None
            if isinstance(item, str):
                symbol = item
                exchange = None
            elif isinstance(item, dict):
                symbol = self._extract_symbol(item)
                exchange = self._extract_exchange(item)
                watchlist_id = self._extract_watchlist_id(item)
                stock_id = self._extract_stock_id(item)
            else:
                continue
            clean_symbol = normalize_symbol(symbol)
            if clean_symbol:
                result.append(
                    {
                        "symbol": clean_symbol,
                        "exchange": self._normalize_exchange(exchange),
                        "watchlist_id": watchlist_id,
                        "stock_id": stock_id,
                        "raw_item": raw_item if isinstance(raw_item, dict) else None,
                    }
                )
        return result

    def limit_symbols(self, symbols: list[str]) -> list[str]:
        return symbols[: self.settings.max_watchlist_symbols]

    def limit_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return items[: self.settings.max_watchlist_symbols]

    def validate_symbol_allowed(
        self,
        requested_symbol: str,
        allowed_symbols: list[str],
        *,
        requested_exchange: str | None = None,
        allowed_items: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str]:
        symbol = normalize_symbol(requested_symbol)
        if allowed_items:
            return self.find_matching_item(symbol, requested_exchange=requested_exchange, allowed_items=allowed_items) is not None, symbol
        return symbol in set(allowed_symbols), symbol

    def find_matching_item(
        self,
        requested_symbol: str,
        *,
        requested_exchange: str | None = None,
        allowed_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        symbol = normalize_symbol(requested_symbol)
        exchange = self._normalize_exchange(requested_exchange)
        for item in allowed_items or []:
            item_symbol = normalize_symbol(item.get("symbol"))
            item_exchange = self._normalize_exchange(item.get("exchange"))
            if item_symbol != symbol:
                continue
            if item_exchange and exchange and item_exchange != exchange:
                continue
            return item
        return None

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

    def _extract_watchlist_id(self, item: dict[str, Any]) -> str | None:
        value = item.get("watchlist_id") or item.get("watchlistId") or item.get("_id") or item.get("id")
        return str(value) if value not in (None, "") else None

    def _extract_stock_id(self, item: dict[str, Any]) -> str | None:
        stock = item.get("stock") or item.get("stock_id")
        if isinstance(stock, dict):
            value = stock.get("id") or stock.get("_id") or stock.get("stock_id") or stock.get("stockId")
            return str(value) if value not in (None, "") else None
        if stock not in (None, "") and not isinstance(stock, str):
            return str(stock)
        value = item.get("stock_id") or item.get("stockId")
        return str(value) if value not in (None, "") else None

    def _normalize_exchange(self, value: Any) -> str | None:
        clean = str(value or "").strip().upper()
        return clean or None
