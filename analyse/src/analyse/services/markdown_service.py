from __future__ import annotations

from typing import Any

from analyse.schemas.common import DEFAULT_DISCLAIMER


class MarkdownService:
    """Tạo Markdown report từ summary. Hiện là rule-based placeholder."""

    def build(self, summary: dict[str, Any]) -> str:
        symbol = summary.get("symbol", "UNKNOWN")
        company = summary.get("company") or "Chưa rõ tên công ty"
        decision = summary.get("system_decision", {})
        return f"""# Báo cáo phân tích cổ phiếu {symbol}

## 1. Thông tin chung

- Mã cổ phiếu: **{symbol}**
- Công ty: **{company}**
- Trạng thái hệ thống: **{decision.get('status', 'CHƯA ĐỦ DỮ LIỆU')}**

## 2. Lưu ý

{summary.get('disclaimer', '')}

## 3. Ghi chú triển khai

Đây là Markdown placeholder. Cần triển khai LLM/rule-based report chi tiết ở bước tiếp theo.
""".strip()

    def finalize_content(self, content: str | None, summary: dict[str, Any]) -> str | None:
        if not content or not content.strip():
            return None

        disclaimer = summary.get("disclaimer") or DEFAULT_DISCLAIMER
        normalized = content.strip()
        if disclaimer not in normalized:
            normalized = f"{normalized}\n\n---\n\n{disclaimer}"
        return normalized
