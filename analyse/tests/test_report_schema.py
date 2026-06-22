from analyse.schemas.report import AnalyseOneReportRequest, ReportGenerateResponse


def test_analyse_one_request_accepts_provider_model_and_aliases():
    request = AnalyseOneReportRequest.model_validate(
        {
            "provider": "gemini",
            "model": "gemini-request",
            "symbol": "FPT",
            "scopeExchange": "HOSE",
            "options": {
                "riskProfile": "medium",
                "timeHorizon": "medium_term",
                "includeExternalResearch": False,
                "renderMarkdown": True,
                "renderHtml": False,
                "capitalVnd": 100000000,
                "riskPerTradePct": 1.0,
                "maxPositionPct": 12.0,
            },
        }
    )

    assert request.provider == "gemini"
    assert request.model == "gemini-request"
    assert request.scope_exchange == "HOSE"
    assert request.options.risk_profile == "medium"
    assert request.options.time_horizon == "medium_term"
    assert request.options.include_external_research is False
    assert request.options.render_markdown is True
    assert request.options.render_html is False
    assert request.options.capital_vnd == 100000000
    assert request.options.risk_per_trade_pct == 1.0
    assert request.options.max_position_pct == 12.0


def test_analyse_one_request_allows_default_provider_from_settings_layer():
    request = AnalyseOneReportRequest.model_validate({"symbol": "FPT", "scopeExchange": "HOSE"})
    assert request.provider is None


def test_report_response_schema_minimal():
    payload = {
        "data": {
            "report_id": "FPT_HOSE_20260618_103000",
            "generated_at": "2026-06-18T10:30:00+07:00",
            "symbol": "FPT",
            "provider": {"name": "openai", "model": "x", "status": "success", "latency_ms": 1},
        }
    }
    response = ReportGenerateResponse.model_validate(payload)
    assert response.code == 200
    assert response.data.symbol == "FPT"
