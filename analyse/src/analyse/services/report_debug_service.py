from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.utils.debug_scrub import scrub_debug_payload, scrub_debug_text
from analyse.utils.symbol_utils import normalize_symbol


class ReportDebugService:
    """Owns ReportService-level debug artifact paths, writes, and scrubbing."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.external_data_debug_save_extraction_json
            or self.settings.vietstock_debug_save_extraction_json
        )

    def build_debug_path(self, *, symbol: str, suffix: str) -> Path:
        clean_symbol = normalize_symbol(symbol)
        clean_suffix = str(suffix or "").lstrip("_")
        return Path(self.settings.report_output_dir) / "debug" / f"{clean_symbol}_{clean_suffix}"

    def write_json_artifact(self, *, path: Path, payload: Any) -> None:
        if not self.enabled:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(scrub_debug_payload(payload), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def write_text_artifact(self, *, path: Path, content: str) -> None:
        if not self.enabled:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scrub_debug_text(content), encoding="utf-8")

    def write_symbol_json_artifact(self, *, symbol: str, suffix: str, payload: Any) -> None:
        self.write_json_artifact(path=self.build_debug_path(symbol=symbol, suffix=suffix), payload=payload)

    def write_symbol_text_artifact(self, *, symbol: str, suffix: str, content: str) -> None:
        self.write_text_artifact(path=self.build_debug_path(symbol=symbol, suffix=suffix), content=content)
