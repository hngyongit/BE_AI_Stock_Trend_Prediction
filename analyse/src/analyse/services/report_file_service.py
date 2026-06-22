from __future__ import annotations

import re
from pathlib import Path


class ReportFileService:
    """Ghi file report ra thư mục cấu hình, chống path traversal qua report_id."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir

    def write_markdown(self, report_id: str, content: str) -> str:
        return self._write(report_id=report_id, content=content, extension=".md")

    def write_html(self, report_id: str, content: str) -> str:
        return self._write(report_id=report_id, content=content, extension=".html")

    def _write(self, *, report_id: str, content: str, extension: str) -> str:
        output_dir = self.ensure_output_dir()
        file_name = f"{self._safe_report_id(report_id)}{extension}"
        target = output_dir / file_name
        self._assert_inside_output_dir(output_dir, target)
        target.write_text(content, encoding="utf-8")
        return target.as_posix()

    def _safe_report_id(self, report_id: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", report_id.strip())
        normalized = normalized.strip("._")
        if not normalized:
            raise ValueError("report_id không hợp lệ để ghi file.")
        return normalized

    def _assert_inside_output_dir(self, output_dir: Path, target: Path) -> None:
        resolved_dir = output_dir.resolve()
        resolved_target = target.resolve()
        try:
            resolved_target.relative_to(resolved_dir)
        except ValueError as exc:
            raise ValueError("Đường dẫn report nằm ngoài REPORT_OUTPUT_DIR.") from exc
