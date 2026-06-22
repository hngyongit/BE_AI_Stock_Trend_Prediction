from fastapi.testclient import TestClient

from analyse.api.dependencies import get_report_service
from analyse.app import create_app
from analyse.schemas.report import (
    DataSourceStatus,
    HtmlReport,
    MarkdownReport,
    ProviderMetadata,
    ReportData,
    ReportGenerateResponse,
)


class FakeReportService:
    async def analyse_one_report(self, payload):
        provider = payload.provider or "openai"
        model = payload.model or ("gpt-4.1-mini" if provider == "openai" else "gemini-1.5-flash")
        return ReportGenerateResponse(
            data=ReportData(
                report_id=f"{payload.symbol}_HOSE_20260622_153000",
                generated_at="2026-06-22T15:30:00+07:00",
                symbol=payload.symbol,
                company="Cong ty Co phan FPT",
                scope_exchange=payload.scope_exchange,
                provider=ProviderMetadata(name=provider, model=model, status="success", latency_ms=1),
                data_sources=[DataSourceStatus(name="Backend /api/watchlists", type="backend_api", status="success")],
                summary={"symbol": payload.symbol},
                markdown_report=MarkdownReport(available=True, output_path="reports/x.md", content="# Bao cao"),
                html_report=HtmlReport(available=True, output_path="reports/x.html", content=None, template_name="template"),
                warnings=[],
            )
        ).model_dump()


def test_analyse_one_endpoint_returns_unified_shape_for_openai_and_gemini():
    app = create_app()
    app.dependency_overrides[get_report_service] = lambda: FakeReportService()
    client = TestClient(app)

    responses = [
        client.post("/api/ai-reports/analyse-one", json={"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"}),
        client.post("/api/ai-reports/analyse-one", json={"provider": "gemini", "symbol": "FPT", "scopeExchange": "HOSE"}),
    ]

    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"code", "message", "data"}
        assert body["data"]["provider"]["status"] == "success"
        assert set(body["data"].keys()) >= {
            "report_id",
            "generated_at",
            "symbol",
            "scope_exchange",
            "provider",
            "summary",
            "markdown_report",
            "html_report",
            "warnings",
        }

    assert responses[0].json()["data"]["provider"]["name"] == "openai"
    assert responses[1].json()["data"]["provider"]["name"] == "gemini"
