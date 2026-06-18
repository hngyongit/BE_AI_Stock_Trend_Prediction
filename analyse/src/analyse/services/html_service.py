from __future__ import annotations

from pathlib import Path
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.schemas.report import HtmlReport


class HtmlService:
    """Tạo HTML report hoặc metadata. Hiện chưa render HTML đầy đủ."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build_metadata(self, report_id: str, summary: dict[str, Any]) -> HtmlReport:
        output_path = Path(self.settings.report_output_dir) / f"{report_id}.html"
        return HtmlReport(
            available=True,
            output_path=str(output_path).replace("\\", "/"),
            content=None,
            template_name="src/analyse/services/html_service.py::build_metadata",
        )
