from __future__ import annotations

import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from analyse.api.dependencies import (
    get_ai_report_history_service,
    get_report_service,
    get_user_identity_service,
    get_visualization_dataset_service,
    get_visualization_signed_url_service,
)
from analyse.app import create_app
from analyse.config.settings import Settings
from analyse.schemas.common import api_error
from analyse.services.visualization_dataset_service import VisualizationDatasetService
from analyse.services.visualization_signed_url_service import VisualizationSignedUrlService


def _sample_report_json(symbol: str = "UNIT", exchange: str = "HOSE", report_id: str = "UNIT_HOSE_report") -> dict:
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "report_id": report_id,
            "generated_at": "2024-03-01T09:00:00+07:00",
            "symbol": symbol,
            "scope_exchange": exchange,
            "provider": {"name": "openai", "model": "test-model", "status": "success"},
            "data_sources": [],
            "warnings": [],
            "summary": {
                "price_history": [
                    {"time": "2024-01-01", "open": 99, "high": 102, "low": 98, "close": 100, "volume": 1000},
                    {"time": "2024-01-02", "open": 100, "high": 103, "low": 99, "close": 101, "volume": 1100},
                ],
                "bctc_3q": {"periods": []},
                "scores": {"overall_score": 70, "score_confidence": 0.8},
                "data_quality": {"missing_fields": [], "warnings": []},
                "data_coverage": {"price_history_points": 2, "financial_periods_count": 0},
            },
        },
    }


class FakeVisualizationReportService:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result
        self.last_user_token = None
        self.calls = 0

    async def analyse_one_report(self, payload, *, user_token: str):
        self.calls += 1
        self.last_user_token = user_token
        if self.result is not None:
            return self.result
        return _sample_report_json(payload.symbol, payload.scope_exchange)


class FakeIdentityService:
    async def resolve_current_user(self, user_token: str):
        return SimpleNamespace(mongo_user_id="user-1", email="user@example.com")


class FakeHistoryService:
    def __init__(self, report_json: dict | None = None) -> None:
        self.report_json = report_json or _sample_report_json()
        self.calls: list[tuple[str, str]] = []

    async def get_history_detail(self, *, current_user, history_id: str):
        self.calls.append(("history_id", history_id))
        report_id = self.report_json.get("data", {}).get("report_id", "UNIT_HOSE_report")
        return SimpleNamespace(id=history_id, report_id=report_id, report_json=self.report_json)

    async def get_history_detail_by_report_id(self, *, current_user, report_id: str):
        self.calls.append(("report_id", report_id))
        return SimpleNamespace(id="history-1", report_id=report_id, report_json=self.report_json)


class MalformedHistoryService:
    async def get_history_detail(self, *, current_user, history_id: str):
        return SimpleNamespace(id=history_id, report_id="BAD_REPORT", report_json={})

    async def get_history_detail_by_report_id(self, *, current_user, report_id: str):
        return SimpleNamespace(id="history-1", report_id=report_id, report_json={})


class NotFoundHistoryService:
    async def get_history_detail(self, *, current_user, history_id: str):
        from analyse.services.ai_report_history_service import AiReportHistoryNotFoundError

        raise AiReportHistoryNotFoundError("missing")

    async def get_history_detail_by_report_id(self, *, current_user, report_id: str):
        from analyse.services.ai_report_history_service import AiReportHistoryNotFoundError

        raise AiReportHistoryNotFoundError("missing")


class UnavailableHistoryService:
    async def get_history_detail(self, *, current_user, history_id: str):
        from analyse.services.ai_report_history_service import AiReportHistoryUnavailableError

        raise AiReportHistoryUnavailableError("storage unavailable")

    async def get_history_detail_by_report_id(self, *, current_user, report_id: str):
        from analyse.services.ai_report_history_service import AiReportHistoryUnavailableError

        raise AiReportHistoryUnavailableError("storage unavailable")


def _client(
    settings: Settings,
    report_service: FakeVisualizationReportService | None = None,
    *,
    recreate_visualization_service_per_request: bool = False,
) -> tuple[TestClient, FakeVisualizationReportService, VisualizationDatasetService, VisualizationSignedUrlService]:
    app = create_app()
    fake_report_service = report_service or FakeVisualizationReportService()
    visualization_service = VisualizationDatasetService(settings)
    signed_url_service = VisualizationSignedUrlService(settings)
    app.dependency_overrides[get_report_service] = lambda: fake_report_service
    app.dependency_overrides[get_user_identity_service] = lambda: FakeIdentityService()
    app.dependency_overrides[get_ai_report_history_service] = lambda: FakeHistoryService()
    if recreate_visualization_service_per_request:
        app.dependency_overrides[get_visualization_dataset_service] = lambda: VisualizationDatasetService(settings)
    else:
        app.dependency_overrides[get_visualization_dataset_service] = lambda: visualization_service
    app.dependency_overrides[get_visualization_signed_url_service] = lambda: signed_url_service
    return TestClient(app), fake_report_service, visualization_service, signed_url_service


def test_visualization_endpoint_requires_authorization_header():
    client, _, _, _ = _client(Settings(_env_file=None))

    response = client.post("/api/ai-reports/analyse-one/visualization-data", json={"provider": "openai", "symbol": "UNIT"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header. Please login again."


def test_visualization_endpoint_returns_chart_ready_dataset_and_preserves_token_flow():
    client, fake_service, _, _ = _client(Settings(_env_file=None))

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"code", "success", "message", "data"}
    assert body["code"] == 200
    assert body["success"] is True
    assert body["data"]["schema_version"] == "visualization.v1"
    assert body["data"]["symbol"] == "UNIT"
    assert {table["name"] for table in body["data"]["tables"]} >= {
        "prices",
        "financial_periods",
        "scores",
        "peers",
        "market_context",
        "ai_signals",
        "data_quality",
    }
    assert fake_service.calls == 0


def test_visualization_endpoint_returns_v2_charts_without_long_warning_blocks():
    client, _, _, _ = _client(Settings(_env_file=None))

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 200
    visualization = response.json()["data"]["visualization"]
    assert visualization["schema_version"] == "visualization.v2"
    assert isinstance(visualization["charts"], list)
    assert "warnings" not in visualization
    assert "missingFields" not in visualization


def test_analyse_one_warms_visualization_cache_so_history_unavailable_does_not_return_503(tmp_path):
    app = create_app()
    settings = Settings(_env_file=None, DATA_FORMULATOR_HOME=str(tmp_path))
    fake_service = FakeVisualizationReportService(_sample_report_json(report_id="WARM_HOSE_report"))
    visualization_service = VisualizationDatasetService(settings)
    app.dependency_overrides[get_report_service] = lambda: fake_service
    app.dependency_overrides[get_user_identity_service] = lambda: FakeIdentityService()
    app.dependency_overrides[get_ai_report_history_service] = lambda: UnavailableHistoryService()
    app.dependency_overrides[get_visualization_dataset_service] = lambda: visualization_service
    client = TestClient(app)

    analyse_response = client.post(
        "/api/ai-reports/analyse-one",
        json={"provider": "openai", "symbol": "WARM", "scopeExchange": "HOSE"},
        headers={"Authorization": "Bearer route-token"},
    )
    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "WARM", "scopeExchange": "HOSE", "options": {"reportId": "WARM_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert analyse_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["data"]["visualization"]["meta"]["cache_hit"] is True
    assert response.json()["data"]["visualization"]["charts"]
    assert fake_service.calls == 1


def test_visualization_endpoint_history_unavailable_cache_miss_returns_404_not_503():
    app = create_app()
    settings = Settings(_env_file=None)
    app.dependency_overrides[get_report_service] = lambda: FakeVisualizationReportService()
    app.dependency_overrides[get_user_identity_service] = lambda: FakeIdentityService()
    app.dependency_overrides[get_ai_report_history_service] = lambda: UnavailableHistoryService()
    app.dependency_overrides[get_visualization_dataset_service] = lambda: VisualizationDatasetService(settings)
    client = TestClient(app)

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "MISS", "scopeExchange": "HOSE", "options": {"reportId": "MISS_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "REPORT_NOT_FOUND"


def test_visualization_endpoint_requires_report_id_without_running_analysis():
    blocked = api_error("Mã không nằm trong watchlist.", "SYMBOL_NOT_IN_WATCHLIST", code=403)
    fake_service = FakeVisualizationReportService(blocked)
    client, _, _, _ = _client(Settings(_env_file=None), fake_service)

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "BLOCKED", "scopeExchange": "HOSE"},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "VISUALIZATION_REPORT_ID_REQUIRED"
    assert fake_service.calls == 0


def test_visualization_feature_flag_disabled_returns_controlled_response():
    client, _, _, _ = _client(Settings(_env_file=None, VISUALIZATION_EXPORT_ENABLED=False))

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE"},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["type"] == "VISUALIZATION_EXPORT_DISABLED"


def test_post_visualization_missing_report_returns_structured_404():
    app = create_app()
    settings = Settings(_env_file=None)
    app.dependency_overrides[get_report_service] = lambda: FakeVisualizationReportService()
    app.dependency_overrides[get_user_identity_service] = lambda: FakeIdentityService()
    app.dependency_overrides[get_ai_report_history_service] = lambda: NotFoundHistoryService()
    app.dependency_overrides[get_visualization_dataset_service] = lambda: VisualizationDatasetService(settings)
    client = TestClient(app)

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "MISS", "scopeExchange": "HOSE", "options": {"reportId": "MISS_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "REPORT_NOT_FOUND"


def test_post_visualization_malformed_report_returns_structured_422():
    app = create_app()
    settings = Settings(_env_file=None)
    app.dependency_overrides[get_report_service] = lambda: FakeVisualizationReportService()
    app.dependency_overrides[get_user_identity_service] = lambda: FakeIdentityService()
    app.dependency_overrides[get_ai_report_history_service] = lambda: MalformedHistoryService()
    app.dependency_overrides[get_visualization_dataset_service] = lambda: VisualizationDatasetService(settings)
    client = TestClient(app)

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "BAD", "scopeExchange": "HOSE", "options": {"reportId": "BAD_REPORT"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "MALFORMED_REPORT_DATA"


def test_history_visualization_malformed_report_returns_structured_422():
    app = create_app()
    settings = Settings(_env_file=None)
    app.dependency_overrides[get_user_identity_service] = lambda: FakeIdentityService()
    app.dependency_overrides[get_ai_report_history_service] = lambda: MalformedHistoryService()
    app.dependency_overrides[get_visualization_dataset_service] = lambda: VisualizationDatasetService(settings)
    client = TestClient(app)

    response = client.get(
        "/api/ai-reports/history/history-1/visualization-data",
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "MALFORMED_REPORT_DATA"


def test_history_visualization_missing_report_returns_structured_404():
    app = create_app()
    settings = Settings(_env_file=None)
    app.dependency_overrides[get_user_identity_service] = lambda: FakeIdentityService()
    app.dependency_overrides[get_ai_report_history_service] = lambda: NotFoundHistoryService()
    app.dependency_overrides[get_visualization_dataset_service] = lambda: VisualizationDatasetService(settings)
    client = TestClient(app)

    response = client.get(
        "/api/ai-reports/history/missing/visualization-data",
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "HISTORY_NOT_FOUND"


def test_history_visualization_first_build_and_cached_response_are_fast(tmp_path):
    settings = Settings(_env_file=None, DATA_FORMULATOR_HOME=str(tmp_path))
    client, fake_service, _, _ = _client(settings)

    started = time.perf_counter()
    first = client.get(
        "/api/ai-reports/history/history-1/visualization-data",
        headers={"Authorization": "Bearer route-token"},
    )
    first_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    second = client.get(
        "/api/ai-reports/history/history-1/visualization-data",
        headers={"Authorization": "Bearer route-token"},
    )
    second_ms = (time.perf_counter() - started) * 1000

    assert first.status_code == 200
    assert second.status_code == 200
    assert first_ms < 1000
    assert second_ms < 300
    assert second_ms <= first_ms
    assert second.json()["data"]["visualization"]["meta"]["cache_hit"] is True
    assert fake_service.calls == 0


def test_visualization_csv_endpoint_returns_selected_table():
    client, _, _, _ = _client(Settings(_env_file=None, VISUALIZATION_CSV_EXPORT_ENABLED=True))

    warm_response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    assert warm_response.status_code == 200

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data.csv?table=prices",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE"},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "date,open,high,low,close,volume" in response.text


def test_visualization_csv_endpoint_uses_cached_dataset_without_rerunning_analysis():
    client, fake_service, _, _ = _client(Settings(_env_file=None, VISUALIZATION_CSV_EXPORT_ENABLED=True))

    warm_response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    assert warm_response.status_code == 200
    assert fake_service.calls == 0

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data.csv?table=prices",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE"},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 200
    assert fake_service.calls == 0


def test_visualization_csv_endpoint_cache_miss_returns_structured_404_without_analysis():
    client, fake_service, _, _ = _client(Settings(_env_file=None, VISUALIZATION_CSV_EXPORT_ENABLED=True))

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data.csv?table=prices",
        json={"provider": "openai", "symbol": "MISS", "scopeExchange": "HOSE"},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "VISUALIZATION_NOT_FOUND"
    assert response.json()["error"]["code"] == "VISUALIZATION_NOT_FOUND"
    assert response.json()["success"] is False
    assert fake_service.calls == 0


def test_visualization_csv_endpoint_loads_file_cache_after_memory_cache_cleared(tmp_path):
    settings = Settings(_env_file=None, DATA_FORMULATOR_HOME=str(tmp_path), VISUALIZATION_CSV_EXPORT_ENABLED=True)
    client, fake_service, visualization_service, _ = _client(settings)

    warm_response = client.post(
        "/api/ai-reports/analyse-one/visualization-data",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    assert warm_response.status_code == 200
    VisualizationDatasetService._shared_dataset_cache.clear()

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data.csv?table=prices",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "date,open,high,low,close,volume" in response.text
    assert fake_service.calls == 0
    assert visualization_service.load_visualization_json_file("UNIT_HOSE_report") is not None


def test_visualization_csv_feature_flag_disabled_returns_controlled_response():
    client, _, _, _ = _client(Settings(_env_file=None, VISUALIZATION_CSV_EXPORT_ENABLED=False))

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data.csv?table=prices",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE"},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["type"] == "VISUALIZATION_CSV_EXPORT_DISABLED"


def test_visualization_signed_url_creation_requires_authorization_header():
    settings = Settings(_env_file=None, DATA_FORMULATOR_ENABLED=True, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, _, _ = _client(settings)

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header. Please login again."


def test_signed_json_read_does_not_require_authorization_and_returns_dataset():
    settings = Settings(_env_file=None, DATA_FORMULATOR_ENABLED=True, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, _, _ = _client(settings)

    create_resp = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    assert create_resp.status_code == 200
    dataset_url = create_resp.json()["data"]["dataset_url"]
    parsed = urlparse(dataset_url)

    read_resp = client.get(parsed.path + ("?" + parsed.query if parsed.query else ""))

    assert read_resp.status_code == 200
    assert read_resp.headers["content-type"].startswith("application/json")
    assert "tables" in read_resp.json()


def test_signed_json_read_works_even_when_visualization_service_recreated_per_request():
    settings = Settings(_env_file=None, DATA_FORMULATOR_ENABLED=True, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, _, _ = _client(settings, recreate_visualization_service_per_request=True)

    create_resp = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    assert create_resp.status_code == 200
    dataset_url = create_resp.json()["data"]["dataset_url"]
    assert ".json?" in dataset_url
    parsed = urlparse(dataset_url)

    read_resp = client.get(parsed.path + ("?" + parsed.query if parsed.query else ""))
    read_resp_2 = client.get(parsed.path + ("?" + parsed.query if parsed.query else ""))

    assert read_resp.status_code == 200
    assert read_resp_2.status_code == 200
    body = read_resp.json()
    assert body["schema_version"] == "visualization.v1"
    assert isinstance(body.get("tables"), list)


def test_signed_url_creation_uses_saved_report_without_rerunning_analysis(tmp_path):
    settings = Settings(_env_file=None, DATA_FORMULATOR_HOME=str(tmp_path), DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    fake_service = FakeVisualizationReportService()
    client, _, _, _ = _client(settings, fake_service)
    VisualizationDatasetService._shared_dataset_cache.clear()
    VisualizationDatasetService._shared_signed_dataset_cache.clear()

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 200
    assert fake_service.calls == 0
    assert response.json()["success"] is True
    assert response.json()["data"]["dataset_url"]


def test_signed_url_creation_missing_dataset_returns_404_without_analysis(tmp_path):
    app = create_app()
    settings = Settings(_env_file=None, DATA_FORMULATOR_HOME=str(tmp_path), DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    fake_service = FakeVisualizationReportService()
    app.dependency_overrides[get_report_service] = lambda: fake_service
    app.dependency_overrides[get_user_identity_service] = lambda: FakeIdentityService()
    app.dependency_overrides[get_ai_report_history_service] = lambda: NotFoundHistoryService()
    app.dependency_overrides[get_visualization_dataset_service] = lambda: VisualizationDatasetService(settings)
    app.dependency_overrides[get_visualization_signed_url_service] = lambda: VisualizationSignedUrlService(settings)
    client = TestClient(app)
    VisualizationDatasetService._shared_dataset_cache.clear()
    VisualizationDatasetService._shared_signed_dataset_cache.clear()

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "MISS", "scopeExchange": "HOSE", "options": {"reportId": "MISS_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "VISUALIZATION_DATASET_NOT_FOUND"
    assert response.json()["error"]["code"] == "VISUALIZATION_DATASET_NOT_FOUND"
    assert fake_service.calls == 0


def test_signed_json_read_loads_persisted_metadata_after_memory_cache_cleared(tmp_path):
    settings = Settings(_env_file=None, DATA_FORMULATOR_HOME=str(tmp_path), DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, fake_service, _, _ = _client(settings)
    create_resp = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    assert create_resp.status_code == 200
    dataset_url = create_resp.json()["data"]["dataset_url"]
    parsed = urlparse(dataset_url)
    VisualizationDatasetService._shared_dataset_cache.clear()
    VisualizationDatasetService._shared_signed_dataset_cache.clear()

    read_resp = client.get(parsed.path + ("?" + parsed.query if parsed.query else ""))

    assert read_resp.status_code == 200
    assert read_resp.json()["symbol"] == "UNIT"
    assert fake_service.calls == 0


def test_signed_csv_read_does_not_require_authorization_and_returns_csv():
    settings = Settings(
        _env_file=None,
        DATA_FORMULATOR_ENABLED=True,
        DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret",
        VISUALIZATION_CSV_EXPORT_ENABLED=True,
    )
    client, _, _, _ = _client(settings)

    create_resp = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    assert create_resp.status_code == 200
    csv_url = create_resp.json()["data"]["csv_urls"]["prices"]
    parsed = urlparse(csv_url)

    read_resp = client.get(parsed.path + ("?" + parsed.query if parsed.query else ""))

    assert read_resp.status_code == 200
    assert read_resp.headers["content-type"].startswith("text/csv")
    assert "date,open,high,low,close,volume" in read_resp.text


def test_signed_read_missing_signature_fails():
    settings = Settings(_env_file=None, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, visualization_service, signed_service = _client(settings)
    dataset = visualization_service.build_from_report_response(FakeVisualizationReportService().result or {
        "code": 200,
        "message": "ok",
        "data": {"symbol": "UNIT", "scope_exchange": "HOSE", "summary": {}},
    })
    dataset_id = signed_service.generate_dataset_id("UNIT", "HOSE")
    visualization_service.store_signed_dataset(dataset_id, dataset, 1800)
    expires = int(time.time()) + 60

    response = client.get(
        f"/api/ai-reports/visualization-datasets/{dataset_id}.json"
        f"?expires={expires}"
    )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "INVALID_SIGNATURE"


def test_signed_json_tampered_dataset_id_fails():
    settings = Settings(_env_file=None, DATA_FORMULATOR_ENABLED=True, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, _, _ = _client(settings)
    create_resp = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    dataset_url = create_resp.json()["data"]["dataset_url"]
    parsed = urlparse(dataset_url)
    tampered_path = parsed.path.replace(".json", "_tampered.json")
    response = client.get(tampered_path + "?" + parsed.query)
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "INVALID_SIGNATURE"


def test_signed_csv_tampered_table_fails():
    settings = Settings(_env_file=None, DATA_FORMULATOR_ENABLED=True, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, _, _ = _client(settings)
    create_resp = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )
    csv_url = create_resp.json()["data"]["csv_urls"]["prices"]
    parsed = urlparse(csv_url)
    params = parse_qs(parsed.query)
    params["table"] = ["scores"]
    query = "&".join(f"{k}={v[0]}" for k, v in params.items())
    response = client.get(parsed.path + "?" + query)
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "INVALID_SIGNATURE"


def test_signed_read_expired_url_fails():
    settings = Settings(_env_file=None, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, visualization_service, signed_service = _client(settings)
    fake_service = FakeVisualizationReportService()
    dataset = visualization_service.build_from_report_response(fake_service.result or {
        "code": 200,
        "message": "ok",
        "data": {"symbol": "UNIT", "scope_exchange": "HOSE", "summary": {}},
    })
    dataset_id = signed_service.generate_dataset_id("UNIT", "HOSE")
    visualization_service.store_signed_dataset(dataset_id, dataset, 1800)
    expires = int(time.time()) - 5
    signature = signed_service._create_signature(
        dataset_id=dataset_id,
        format="json",
        expires=expires,
    )
    response = client.get(
        f"/api/ai-reports/visualization-datasets/{dataset_id}.json"
        f"?expires={expires}&signature={signature}"
    )
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "INVALID_SIGNATURE"


def test_signed_csv_invalid_table_fails():
    settings = Settings(_env_file=None, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, visualization_service, signed_service = _client(settings)
    fake_service = FakeVisualizationReportService()
    dataset = visualization_service.build_from_report_response(fake_service.result or {
        "code": 200,
        "message": "ok",
        "data": {"symbol": "UNIT", "scope_exchange": "HOSE", "summary": {}},
    })
    dataset_id = signed_service.generate_dataset_id("UNIT", "HOSE")
    visualization_service.store_signed_dataset(dataset_id, dataset, 1800)
    expires = int(time.time()) + 60
    signature = signed_service._create_csv_signature(
        dataset_id=dataset_id,
        format="csv",
        table="bad_table",
        expires=expires,
    )
    response = client.get(
        f"/api/ai-reports/visualization-datasets/{dataset_id}.csv"
        f"?table=bad_table&expires={expires}&signature={signature}"
    )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "INVALID_TABLE"


def test_signed_read_missing_secret_fails_safely():
    settings = Settings(_env_file=None, DATA_FORMULATOR_SIGNED_URL_SECRET="")
    client, _, _, _ = _client(settings)
    response = client.get(
        "/api/ai-reports/visualization-datasets/any.json"
        "?expires=9999999999&signature=abc"
    )
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "SIGNED_URL_NOT_CONFIGURED"


def test_signed_url_response_does_not_leak_bearer_token():
    settings = Settings(_env_file=None, DATA_FORMULATOR_ENABLED=True, DATA_FORMULATOR_SIGNED_URL_SECRET="test-secret")
    client, _, _, _ = _client(settings)

    response = client.post(
        "/api/ai-reports/analyse-one/visualization-data/signed-url",
        json={"provider": "openai", "symbol": "UNIT", "scopeExchange": "HOSE", "options": {"reportId": "UNIT_HOSE_report"}},
        headers={"Authorization": "Bearer route-token"},
    )

    assert response.status_code == 200
    payload = str(response.json())
    assert "route-token" not in payload
    assert "Authorization" not in payload
    assert "data_formulator_import_url" not in payload
    assert "auto_import_supported" not in payload
    assert "session_supported" not in payload
    assert "session_url" not in payload
    assert "bridge_url" not in payload
