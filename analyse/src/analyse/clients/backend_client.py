from __future__ import annotations

from typing import Any

import httpx

from analyse.config.settings import Settings, get_settings


class BackendAPIClient:
    """Skeleton client de goi Node.js backend API hien co."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.backend_api_url.rstrip("/")
        self.token = self.settings.backend_api_token

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def get_stock_detail(self, symbol: str) -> dict[str, Any]:
        """TODO: Goi GET /api/stocks/:symbol de lay stock va latest_price."""
        raise NotImplementedError("Chua trien khai logic goi backend API cho stock detail.")

    async def get_stock_chart(self, symbol: str, range_value: str = "1m") -> list[dict[str, Any]]:
        """TODO: Goi GET /api/stocks/:symbol/chart?range=... de lay OHLCV."""
        raise NotImplementedError("Chua trien khai logic goi backend API cho stock chart.")

    async def get_watchlist(self) -> dict[str, Any]:
        """TODO: Goi GET /api/watchlists. Endpoint nay can Bearer token cua user."""
        raise NotImplementedError("Chua trien khai logic goi backend API cho watchlist.")

    async def get_user_dashboard(self) -> dict[str, Any]:
        """TODO: Goi GET /api/dashboard/user neu can market_leaders va market_overview."""
        raise NotImplementedError("Chua trien khai logic goi backend API cho user dashboard.")

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ham dung chung cho giai doan sau; hien chua duoc route nao su dung."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()
