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
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, dict):
            items = data.get("items") or data.get("watchlist") or data.get("stocks") or []
        else:
            items = data or []

        symbols: list[str | None] = []
        for item in items:
            if isinstance(item, str):
                symbols.append(item)
            elif isinstance(item, dict):
                symbols.append(item.get("symbol") or item.get("code") or item.get("stockSymbol"))
        return normalize_symbols(symbols)

    def limit_symbols(self, symbols: list[str]) -> list[str]:
        return symbols[: self.settings.max_watchlist_symbols]

    def validate_symbol_allowed(self, requested_symbol: str, allowed_symbols: list[str]) -> tuple[bool, str]:
        symbol = normalize_symbol(requested_symbol)
        return symbol in set(allowed_symbols), symbol

    def build_placeholder_result(self, stocks: list[WatchlistStockItem]) -> dict[str, Any]:
        symbols = normalize_symbols([item.symbol for item in stocks])
        return {
            "summary": "Watchlist placeholder: service đã nhận danh sách mã, phân tích AI sẽ triển khai sau.",
            "allowed_symbols": self.limit_symbols(symbols),
            "total_symbols_received": len(symbols),
        }
