from __future__ import annotations

from typing import Any

import httpx


class HttpClientError(RuntimeError):
    """Lỗi HTTP đã được phân loại để chẩn đoán cấu hình/kết nối an toàn hơn."""

    def __init__(
        self,
        *,
        method: str,
        url: str,
        category: str,
        message: str,
        status_code: int | None = None,
    ) -> None:
        self.method = method
        self.url = url
        self.category = category
        self.status_code = status_code
        self.message = message
        super().__init__(f"{method} {url} failed: {category}: {message}")

    def diagnostic(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "method": self.method,
            "url": self.url,
            "category": self.category,
            "message": self.message,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


class HttpClient:
    """HTTP helper dùng chung cho Backend API và nguồn research public."""

    def __init__(self, timeout_ms: int = 30000, *, verify_ssl: bool = True) -> None:
        self.timeout_seconds = timeout_ms / 1000
        self.verify_ssl = verify_ssl

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self._get(url, headers=headers, params=params)
        return response.json()

    async def get_text(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> str:
        response = await self._get(url, headers=headers, params=params)
        return response.text

    async def _get(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> httpx.Response:
        method = "GET"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, verify=self.verify_ssl) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else None
            category = "unauthorized" if status_code == 401 else "not_found" if status_code == 404 else "http_status"
            raise HttpClientError(
                method=method,
                url=str(exc.request.url),
                category=category,
                status_code=status_code,
                message=f"HTTP {status_code}",
            ) from exc
        except httpx.ConnectTimeout as exc:
            raise HttpClientError(method=method, url=url, category="connect_timeout", message="connection timed out") from exc
        except httpx.ReadTimeout as exc:
            raise HttpClientError(method=method, url=url, category="read_timeout", message="read timed out") from exc
        except httpx.ConnectError as exc:
            message = str(exc).strip() or "connection failed"
            if "All connection attempts failed" in message:
                message = "connection refused or backend unreachable"
            raise HttpClientError(method=method, url=url, category="connection_failed", message=message) from exc
        except httpx.RequestError as exc:
            raise HttpClientError(method=method, url=url, category="request_error", message=str(exc) or exc.__class__.__name__) from exc
