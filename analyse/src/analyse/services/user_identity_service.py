from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from analyse.clients.backend_client import BackendClient
from analyse.clients.http_client import HttpClientError


class UserIdentityError(RuntimeError):
    """Base error for current-user identity resolution."""


class UserIdentityUnauthorizedError(UserIdentityError):
    """Backend rejected the user token."""


class UserIdentityMalformedError(UserIdentityError):
    """Backend current-user response did not include a usable user id."""


@dataclass(frozen=True)
class CurrentUserIdentity:
    mongo_user_id: str
    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    plan: str | None = None


class UserIdentityService:
    """Resolve the Mongo-backed current user from the request token."""

    def __init__(self, backend_client: BackendClient) -> None:
        self.backend_client = backend_client

    async def resolve_current_user(self, token: str) -> CurrentUserIdentity:
        try:
            payload = await self.backend_client.get_current_user(token=token)
        except HttpClientError as exc:
            if exc.status_code == 401 or exc.category == "unauthorized":
                raise UserIdentityUnauthorizedError("Phiên đăng nhập đã hết hạn hoặc token không hợp lệ.") from exc
            raise UserIdentityError("Không xác thực được người dùng từ Backend.") from exc
        except Exception as exc:
            if self._looks_like_auth_error(exc):
                raise UserIdentityUnauthorizedError("Phiên đăng nhập đã hết hạn hoặc token không hợp lệ.") from exc
            raise UserIdentityError("Không xác thực được người dùng từ Backend.") from exc

        return self.normalize_current_user(payload)

    def normalize_current_user(self, payload: Any) -> CurrentUserIdentity:
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            raise UserIdentityMalformedError("Backend current-user response không hợp lệ.")

        user_id = data.get("id") or data.get("_id") or data.get("user_id") or data.get("userId")
        mongo_user_id = str(user_id or "").strip()
        if not mongo_user_id:
            raise UserIdentityMalformedError("Backend current-user response thiếu data.id.")

        return CurrentUserIdentity(
            mongo_user_id=mongo_user_id,
            email=self._clean_optional(data.get("email")),
            full_name=self._clean_optional(data.get("full_name") or data.get("fullName") or data.get("name")),
            role=self._clean_optional(data.get("role")),
            plan=self._clean_optional(data.get("plan")),
        )

    def _looks_like_auth_error(self, exc: Exception) -> bool:
        detail = str(exc).lower()
        status_code = getattr(exc, "status_code", None)
        category = str(getattr(exc, "category", "") or "").lower()
        return status_code == 401 or category == "unauthorized" or "401" in detail or "unauthorized" in detail

    def _clean_optional(self, value: Any) -> str | None:
        clean = str(value or "").strip()
        return clean or None
