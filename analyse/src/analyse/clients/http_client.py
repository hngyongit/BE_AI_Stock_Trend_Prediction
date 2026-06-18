from __future__ import annotations

from typing import Any

import httpx


class HttpClient:
    """HTTP helper dùng chung cho Backend API và nguồn research public."""

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_seconds = timeout_ms / 1000

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_text(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> str:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.text
