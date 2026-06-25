from __future__ import annotations

import asyncio

from analyse.config.settings import Settings
from analyse.services.report_assembly_service import ReportAssemblyService
from analyse.services.source_collection_coordinator import SourceCollectionCoordinator, SourceCollectionResult


def test_source_collection_result_defaults_are_isolated_lists():
    first = SourceCollectionResult()
    second = SourceCollectionResult()

    first.warnings.append("one warning")
    first.source_statuses.append({"name": "Backend"})
    first.data_source_statuses.append({"name": "Backend detail"})
    first.debug_payload["token"] = "redacted"
    first.evidence_table.append({"source_name": "Vietstock"})
    first.source_backed_warnings.append("one source-backed warning")
    first.source_backed_debug_payload["evidence_count"] = 1

    assert second.warnings == []
    assert second.source_statuses == []
    assert second.data_source_statuses == []
    assert second.debug_payload == {}
    assert second.evidence_table == []
    assert second.source_backed_warnings == []
    assert second.source_backed_debug_payload == {}


def test_source_collection_coordinator_skeleton_returns_empty_result(tmp_path):
    coordinator = SourceCollectionCoordinator(Settings(REPORT_OUTPUT_DIR=str(tmp_path / "reports")))

    result = asyncio.run(
        coordinator.collect_for_analyse_one(
            symbol="FPT",
            exchange="HOSE",
            token="request-token",
            options=None,
        )
    )

    assert isinstance(result, SourceCollectionResult)
    assert result.backend_stock_payload is None
    assert result.warnings == []


def test_report_assembly_service_skeleton_returns_empty_payload(tmp_path):
    service = ReportAssemblyService(Settings(REPORT_OUTPUT_DIR=str(tmp_path / "reports")))

    result = asyncio.run(
        service.build_report_summary_and_presentation(
            symbol="FPT",
            payload={"symbol": "FPT"},
            source_result=SourceCollectionResult(),
            llm_result=None,
        )
    )

    assert result == {}
