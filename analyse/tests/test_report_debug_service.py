from __future__ import annotations

import json

from analyse.config.settings import Settings
from analyse.services.report_debug_service import ReportDebugService


def test_build_debug_path_normalizes_symbol_and_suffix(tmp_path):
    service = ReportDebugService(Settings(REPORT_OUTPUT_DIR=str(tmp_path / "reports")))

    path = service.build_debug_path(symbol=" fpt ", suffix="_backend_urls.json")

    assert path == tmp_path / "reports" / "debug" / "FPT_backend_urls.json"


def test_write_json_artifact_noops_when_debug_disabled(tmp_path):
    service = ReportDebugService(
        Settings(
            REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
            EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=False,
            VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=False,
        )
    )
    path = service.build_debug_path(symbol="FPT", suffix="payload.json")

    service.write_json_artifact(path=path, payload={"symbol": "FPT"})

    assert not path.exists()


def test_write_json_artifact_scrubs_payload_when_enabled(tmp_path):
    service = ReportDebugService(
        Settings(
            REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
            EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        )
    )
    path = service.build_debug_path(symbol="FPT", suffix="payload.json")

    service.write_json_artifact(
        path=path,
        payload={
            "symbol": "FPT",
            "Authorization": "Bearer SHOULD_NOT_LEAK",
            "url": "https://example.com?token=secret&symbol=FPT",
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["symbol"] == "FPT"
    assert "SHOULD_NOT_LEAK" not in serialized
    assert "secret" not in serialized


def test_write_text_artifact_scrubs_content_when_enabled(tmp_path):
    service = ReportDebugService(
        Settings(
            REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
            VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=True,
        )
    )
    path = service.build_debug_path(symbol="VCB", suffix="raw.txt")

    service.write_text_artifact(path=path, content="Authorization: Bearer SHOULD_NOT_LEAK")

    text = path.read_text(encoding="utf-8")
    assert "SHOULD_NOT_LEAK" not in text
