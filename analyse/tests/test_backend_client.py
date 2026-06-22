from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    async def get_json(self, url, *, headers=None, params=None):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        return {"code": 200, "message": "ok", "data": {"symbol": "FPT"}}


def test_backend_client_builds_headers_without_token():
    client = BackendClient(Settings(BACKEND_API_TOKEN=None))
    assert client._headers() == {"Accept": "application/json"}


def test_backend_client_builds_headers_with_token():
    client = BackendClient(Settings(BACKEND_API_TOKEN="abc"))
    assert client._headers()["Authorization"] == "Bearer abc"


def test_backend_client_does_not_duplicate_bearer_scheme():
    client = BackendClient(Settings(BACKEND_API_TOKEN="Bearer abc"))
    assert client._headers()["Authorization"] == "Bearer abc"


def test_backend_client_respects_custom_auth_scheme():
    client = BackendClient(Settings(BACKEND_API_TOKEN="abc", BACKEND_API_AUTH_SCHEME="Token"))
    assert client._headers()["Authorization"] == "Token abc"


def test_backend_client_builds_configured_urls():
    client = BackendClient(Settings(BACKEND_API_BASE_URL="http://localhost:5000"))
    assert client._url("/api/watchlists") == "http://localhost:5000/api/watchlists"


def test_backend_client_calls_analysis_data_with_expected_query_params():
    fake_http = FakeHttpClient()
    client = BackendClient(
        Settings(BACKEND_API_BASE_URL="http://localhost:5000", BACKEND_API_TOKEN="abc"),
        http_client=fake_http,
    )

    import asyncio

    payload = asyncio.run(
        client.get_stock_analysis_data(
            "fpt",
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

    asyncio.run(client.get_stock_chart("FPT", range_value="3m"))

    assert fake_http.calls[0]["url"] == "http://localhost:5000/api/stocks/FPT/chart"
    assert fake_http.calls[0]["params"] == {"range": "3m"}
