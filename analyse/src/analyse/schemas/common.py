from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ProviderName = Literal["openai", "gemini"]
SourceStatus = Literal["success", "partial", "insufficient", "failed", "disabled", "not_configured", "skipped", "not_implemented"]

DEFAULT_DISCLAIMER = "Báo cáo này chỉ phục vụ tham khảo/học tập, không phải khuyến nghị đầu tư cá nhân hóa."


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    type: str
    code: str | None = None
    details: list[ErrorDetail] = Field(default_factory=list)


class APIErrorResponse(BaseModel):
    code: int
    success: bool = False
    message: str
    error: ErrorBody
    data: None = None


def api_success(message: str, data: Any | None = None, code: int = 200) -> dict[str, Any]:
    return {"code": code, "success": True, "message": message, "data": data}


def api_error(message: str, error_type: str, *, code: int = 400, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "success": False,
        "message": message,
        "error": {"type": error_type, "code": error_type, "details": details or []},
        "data": None,
    }
