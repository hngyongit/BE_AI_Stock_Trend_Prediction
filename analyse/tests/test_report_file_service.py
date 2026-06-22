from pathlib import Path

import pytest

from analyse.services.report_file_service import ReportFileService


def test_report_file_service_creates_output_dir_and_markdown(tmp_path):
    output_dir = tmp_path / "reports"
    service = ReportFileService(output_dir)

    output_path = service.write_markdown("FPT_HOSE_20260622_105312", "# Báo cáo FPT")

    path = Path(output_path)
    assert path.exists()
    assert path.suffix == ".md"
    assert path.read_text(encoding="utf-8") == "# Báo cáo FPT"


def test_report_file_service_creates_html(tmp_path):
    output_dir = tmp_path / "reports"
    service = ReportFileService(output_dir)

    output_path = service.write_html("FPT_HOSE_20260622_105312", "<!doctype html><html lang=\"vi\"></html>")

    path = Path(output_path)
    assert path.exists()
    assert path.suffix == ".html"
    assert "<!doctype html>" in path.read_text(encoding="utf-8")


def test_report_file_service_returns_relative_path_for_relative_output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = ReportFileService("reports")

    output_path = service.write_html("FPT_HOSE_20260622_105312", "<!doctype html><html lang=\"vi\"></html>")

    assert output_path == "reports/FPT_HOSE_20260622_105312.html"
    assert Path(output_path).exists()


def test_report_file_service_rejects_empty_report_id(tmp_path):
    service = ReportFileService(tmp_path / "reports")

    with pytest.raises(ValueError):
        service.write_markdown("../", "unsafe")
