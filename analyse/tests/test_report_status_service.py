from __future__ import annotations

from analyse.services.report_status_service import ReportStatusService


def test_content_exists_without_warnings_is_success():
    status = ReportStatusService().build_report_status(has_report_content=True)

    assert status["analysis_status"] == "success"
    assert status["source_status"] == "success"
    assert status["history_status"] == "disabled"
    assert status["report_status"] == "success"
    assert status["warnings"] == []


def test_content_exists_with_source_partial_is_non_failed_warning_status():
    status = ReportStatusService().build_report_status(
        has_report_content=True,
        source_status="partial",
        source_warnings=["CafeF tài chính chưa đủ dữ liệu."],
    )

    assert status["report_status"] == "success_with_warnings"
    assert status["analysis_status"] == "success"
    assert status["warnings"] == ["CafeF tài chính chưa đủ dữ liệu."]


def test_content_exists_with_history_failed_is_non_failed_warning_status():
    status = ReportStatusService().build_report_status(
        has_report_content=True,
        history_status="failed",
        history_warning="Báo cáo đã phân tích thành công nhưng chưa lưu được lịch sử.",
    )

    assert status["report_status"] == "success_with_warnings"
    assert status["history_status"] == "failed"
    assert status["warnings"] == ["Báo cáo đã phân tích thành công nhưng chưa lưu được lịch sử."]


def test_no_content_with_analysis_error_is_failed():
    status = ReportStatusService().build_report_status(
        has_report_content=False,
        analysis_error=RuntimeError("provider failed"),
        source_status="success",
        history_status="disabled",
    )

    assert status["analysis_status"] == "failed"
    assert status["report_status"] == "failed"
    assert status["warnings"] == ["provider failed"]


def test_warnings_are_preserved_deduped_and_scrubbed():
    status = ReportStatusService().build_report_status(
        has_report_content=True,
        source_warnings=[
            "External source failed",
            "Authorization: Bearer abc.def.secret",
            "External source failed",
        ],
        history_warning="password=my-secret",
    )

    assert status["warnings"][0] == "External source failed"
    assert "abc.def.secret" not in " ".join(status["warnings"])
    assert "my-secret" not in " ".join(status["warnings"])


def test_aggregate_source_status_matches_existing_report_service_policy():
    service = ReportStatusService()

    assert service.aggregate_source_status([]) == "partial"
    assert service.aggregate_source_status([{"name": "Backend", "type": "backend", "status": "failed"}]) == "failed"
    assert service.aggregate_source_status([{"name": "External Research", "type": "news", "status": "disabled"}]) == "partial"
    assert service.aggregate_source_status([{"name": "Backend", "type": "backend_api", "status": "success"}]) == "success"
