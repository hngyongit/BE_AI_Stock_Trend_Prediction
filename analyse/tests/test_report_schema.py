from analyse.schemas.report import AnalyseOneReportRequest, ReportGenerateResponse


def test_analyse_one_request_accepts_aliases():
    request = AnalyseOneReportRequest.model_validate({"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})
    assert request.symbol == "FPT"
    assert request.scope_exchange == "HOSE"


def test_report_response_schema_minimal():
    payload = {
        "data": {
            "report_id": "FPT_HOSE_20260618_103000",
            "generated_at": "2026-06-18T10:30:00+07:00",
            "symbol": "FPT",
            "provider": {"name": "openai", "model": "x", "status": "success", "latency_ms": 1}
        }
    }
    response = ReportGenerateResponse.model_validate(payload)
    assert response.code == 200
    assert response.data.symbol == "FPT"
