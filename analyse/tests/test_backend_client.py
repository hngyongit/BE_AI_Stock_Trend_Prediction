from analyse.clients.backend_client import BackendClient
from analyse.clients.http_client import HttpClientError
from analyse.config.settings import Settings
import pytest


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    async def get_json(self, url, *, headers=None, params=None):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        return {"code": 200, "message": "ok", "data": {"symbol": "FPT"}}


def test_backend_client_builds_headers_without_request_token():
    client = BackendClient(Settings(BACKEND_API_TOKEN="env-token"))
    assert client._headers() == {"Accept": "application/json"}


def test_backend_client_builds_headers_with_request_token():
    client = BackendClient(Settings(BACKEND_API_TOKEN="env-token"))
    assert client._headers("abc")["Authorization"] == "Bearer abc"


def test_backend_client_does_not_duplicate_bearer_scheme():
    client = BackendClient(Settings(BACKEND_API_TOKEN=None))
    assert client._headers("Bearer abc")["Authorization"] == "Bearer abc"


def test_backend_client_uses_bearer_for_request_token_even_if_env_scheme_exists():
    client = BackendClient(Settings(BACKEND_API_TOKEN="env-token", BACKEND_API_AUTH_SCHEME="Token"))
    assert client._headers("abc")["Authorization"] == "Bearer abc"


def test_backend_client_builds_configured_urls():
    client = BackendClient(Settings(BACKEND_API_BASE_URL="http://localhost:5000"))
    assert client._url("/api/watchlists") == "http://localhost:5000/api/watchlists"


def test_backend_client_normalizes_base_url_without_duplicate_api_prefix():
    client = BackendClient(Settings(BACKEND_API_BASE_URL="http://localhost:5000/api/"))
    assert client._url("/api/watchlists") == "http://localhost:5000/api/watchlists"


def test_backend_client_rejects_base_url_without_scheme():
    with pytest.raises(ValueError, match="BACKEND_API_BASE_URL"):
        BackendClient(Settings(BACKEND_API_BASE_URL="localhost:5000"))


def test_backend_client_builds_analysis_data_url_example():
    client = BackendClient(Settings(BACKEND_API_BASE_URL="http://localhost:5000/api"))
    url = client.build_stock_analysis_data_url("hpg", exchange="hose", quarters=6, chart_range="3m")

    assert url.startswith("http://localhost:5000/api/stocks/HPG/analysis-data?")
    assert "exchange=HOSE" in url
    assert "includePeers=true" in url


def test_http_client_error_diagnostic_is_sanitized():
    error = HttpClientError(method="GET", url="http://localhost:5000/api/stocks/HPG", category="connection_failed", message="connection refused")

    diagnostic = error.diagnostic()

    assert diagnostic["category"] == "connection_failed"
    assert "connection refused" in diagnostic["message"]


def test_backend_client_calls_analysis_data_with_expected_query_params():
    fake_http = FakeHttpClient()
    client = BackendClient(
        Settings(BACKEND_API_BASE_URL="http://localhost:5000", BACKEND_API_TOKEN="env-token"),
        http_client=fake_http,
    )

    import asyncio

    payload = asyncio.run(
        client.get_stock_analysis_data(
            "fpt",
            token="abc",
            exchange="HOSE",
            quarters=6,
            chart_range="3m",
            include_peers=True,
            include_market_context=True,
        )
    )

    assert payload["data"]["symbol"] == "FPT"
    call = fake_http.calls[0]
    assert call["url"] == "http://localhost:5000/api/stocks/FPT/analysis-data"
    assert call["headers"]["Authorization"] == "Bearer abc"
    assert call["params"] == {
        "exchange": "HOSE",
        "quarters": 6,
        "chartRange": "3m",
        "includePeers": "true",
        "includeMarketContext": "true",
    }


def test_backend_client_stock_chart_supports_query_param_endpoint():
    fake_http = FakeHttpClient()
    client = BackendClient(
        Settings(BACKEND_API_BASE_URL="http://localhost:5000", BACKEND_STOCK_CHART_ENDPOINT="/api/stocks/{symbol}/chart"),
        http_client=fake_http,
    )

    import asyncio

    asyncio.run(client.get_stock_chart("FPT", range_value="3m", token="abc"))

    assert fake_http.calls[0]["url"] == "http://localhost:5000/api/stocks/FPT/chart"
    assert fake_http.calls[0]["params"] == {"range": "3m"}


def test_backend_client_requires_request_token_for_protected_calls():
    client = BackendClient(Settings(BACKEND_API_BASE_URL="http://localhost:5000", BACKEND_API_TOKEN="env-token"))

    import asyncio

    with pytest.raises(ValueError, match="Backend user token is required"):
        asyncio.run(client.get_watchlists(token=""))


def test_backend_client_watchlists_uses_request_token_not_env_token():
    fake_http = FakeHttpClient()
    client = BackendClient(
        Settings(BACKEND_API_BASE_URL="http://localhost:5000", BACKEND_API_TOKEN="env-token"),
        http_client=fake_http,
    )

    import asyncio

    asyncio.run(client.get_watchlists(token="request-token"))

    call = fake_http.calls[0]
    assert call["url"] == "http://localhost:5000/api/watchlists"
    assert call["headers"]["Authorization"] == "Bearer request-token"
    assert "env-token" not in str(call)


def test_backend_client_get_current_user_uses_configured_endpoint_and_request_token():
    fake_http = FakeHttpClient()
    client = BackendClient(
        Settings(BACKEND_API_BASE_URL="http://localhost:5000/api", BACKEND_CURRENT_USER_ENDPOINT="/api/users/me"),
        http_client=fake_http,
    )

    import asyncio

    asyncio.run(client.get_current_user(token="request-token"))

    call = fake_http.calls[0]
    assert call["url"] == "http://localhost:5000/api/users/me"
    assert call["headers"]["Authorization"] == "Bearer request-token"
    assert "request-token" not in str(client.sanitized_diagnostics())
