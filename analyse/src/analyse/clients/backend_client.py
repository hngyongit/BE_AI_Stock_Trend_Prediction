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
        if self.settings.backend_api_token:
            headers["Authorization"] = f"Bearer {self.settings.backend_api_token}"
        return headers

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    async def get_watchlists(self) -> dict[str, Any]:
        path = self.settings.backend_watchlist_endpoint
        return await self.http_client.get_json(self._url(path), headers=self._headers())

    async def get_stock_detail(self, symbol: str) -> dict[str, Any]:
        path = self.settings.backend_stock_detail_endpoint.format(symbol=symbol.upper())
        return await self.http_client.get_json(self._url(path), headers=self._headers())

    async def get_stock_chart(self, symbol: str, range_value: str = "1m") -> dict[str, Any]:
        path = self.settings.backend_stock_chart_endpoint.format(symbol=symbol.upper(), range=range_value)
        return await self.http_client.get_json(self._url(path), headers=self._headers())
