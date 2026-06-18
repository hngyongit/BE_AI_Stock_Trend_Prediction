from __future__ import annotations

from typing import Any


def build_json_schema_instruction(schema: dict[str, Any] | None = None) -> str:
    if not schema:
        return "Output phải là JSON object hợp lệ."
    return "Output phải tuân thủ JSON schema đã cung cấp, không thêm markdown hoặc text ngoài JSON."
