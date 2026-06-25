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
    def __init__(self) -> None:
        self.last_user_token = None

    async def analyse_one_report(self, payload, *, user_token: str):
        self.last_user_token = user_token
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
    fake_service = FakeReportService()
    app.dependency_overrides[get_report_service] = lambda: fake_service
    client = TestClient(app)

    responses = [
        client.post(
            "/api/ai-reports/analyse-one",
            json={"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"},
            headers={"Authorization": "Bearer route-token"},
        ),
        client.post(
            "/api/ai-reports/analyse-one",
            json={"provider": "gemini", "symbol": "FPT", "scopeExchange": "HOSE"},
            headers={"Authorization": "Bearer route-token"},
        ),
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
    assert fake_service.last_user_token == "route-token"


def test_analyse_one_requires_authorization_header():
    app = create_app()
    app.dependency_overrides[get_report_service] = lambda: FakeReportService()
    client = TestClient(app)

    response = client.post("/api/ai-reports/analyse-one", json={"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header. Please login again."


def test_analyse_one_rejects_invalid_authorization_header_format():
    app = create_app()
    app.dependency_overrides[get_report_service] = lambda: FakeReportService()
    client = TestClient(app)

    response = client.post(
        "/api/ai-reports/analyse-one",
        json={"provider": "openai", "symbol": "FPT", "scopeExchange": "HOSE"},
        headers={"Authorization": "Token abc"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Authorization header format. Expected: Bearer <token>."


def test_analyse_one_cors_preflight_from_vite_origin():
    app = create_app()
    app.dependency_overrides[get_report_service] = lambda: FakeReportService()
    client = TestClient(app)
    cors_middleware = [middleware for middleware in app.user_middleware if middleware.cls.__name__ == "CORSMiddleware"]

    response = client.options(
        "/api/ai-reports/analyse-one",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert len(cors_middleware) == 1
    assert response.status_code in {200, 204}
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_legacy_placeholder_endpoints_return_clear_501_and_are_hidden_from_docs():
    app = create_app()
    client = TestClient(app)

    cases = [
        ("/api/analyse/stock", {"symbol": "FPT", "data": {}}),
        ("/api/analyse/watchlist", {"stocks": [{"symbol": "FPT"}]}),
        ("/api/analyse/fetch-and-analyse/stock", {"symbol": "FPT"}),
    ]

    for path, payload in cases:
        response = client.post(path, json=payload)

        assert response.status_code == 501
        body = response.json()
        assert body["code"] == 501
        assert body["error"]["type"] == "NOT_IMPLEMENTED"
        assert body["data"] is None

    schema = client.get("/openapi.json").json()
    assert "/api/analyse/stock" not in schema["paths"]
    assert "/api/analyse/watchlist" not in schema["paths"]
    assert "/api/analyse/fetch-and-analyse/stock" not in schema["paths"]
