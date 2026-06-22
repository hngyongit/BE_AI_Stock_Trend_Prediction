from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from analyse.clients.http_client import HttpClient
from analyse.config.settings import Settings, get_settings


class BackendClient:
    """Client gọi Node.js Backend API hiện có."""

    def __init__(self, settings: Settings | None = None, http_client: HttpClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.backend_api_base_url.rstrip("/")
        self.http_client = http_client or HttpClient(timeout_ms=self.settings.backend_api_timeout_ms)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        auth_value = self._authorization_header()
        if auth_value:
            headers["Authorization"] = auth_value
        return headers

    def _authorization_header(self) -> str | None:
        token = (self.settings.backend_api_token or "").strip()
        if not token:
            return None

        if token.lower().startswith("bearer "):
            return token

        scheme = (self.settings.backend_api_auth_scheme or "").strip()
        if not scheme:
            return token
        if token.lower().startswith(f"{scheme.lower()} "):
            return token
        return f"{scheme} {token}"

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    async def get_watchlists(self) -> dict[str, Any]:
        path = self.settings.backend_watchlist_endpoint
        return await self.http_client.get_json(self._url(path), headers=self._headers())

    async def get_stock_detail(self, symbol: str) -> dict[str, Any]:
        path = self.settings.backend_stock_detail_endpoint.format(symbol=symbol.upper())
        return await self.http_client.get_json(self._url(path), headers=self._headers())

    async def get_stock_chart(self, symbol: str, range_value: str = "1m") -> dict[str, Any]:
        endpoint = self.settings.backend_stock_chart_endpoint
        if "{range}" in endpoint:
            path = endpoint.format(symbol=symbol.upper(), range=range_value)
            params = None
        else:
            path = endpoint.format(symbol=symbol.upper())
            params = {"range": range_value}
        return await self.http_client.get_json(self._url(path), headers=self._headers(), params=params)

    async def get_stock_analysis_data(
        self,
        symbol: str,
        exchange: str | None = None,
        quarters: int = 6,
        chart_range: str = "3m",
        include_peers: bool = True,
        include_market_context: bool = True,
    ) -> dict[str, Any]:
        path = self.settings.backend_analysis_data_endpoint.format(symbol=symbol.upper())
        params: dict[str, Any] = {
            "quarters": quarters,
            "chartRange": chart_range,
            "includePeers": str(include_peers).lower(),
            "includeMarketContext": str(include_market_context).lower(),
        }
        if exchange:
            params["exchange"] = exchange.upper()
        return await self.http_client.get_json(self._url(path), headers=self._headers(), params=params)
