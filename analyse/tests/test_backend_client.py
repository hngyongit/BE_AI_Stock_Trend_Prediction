from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings


def test_backend_client_builds_headers_without_token():
    client = BackendClient(Settings(BACKEND_API_TOKEN=None))
    assert client._headers() == {"Accept": "application/json"}


def test_backend_client_builds_headers_with_token():
    client = BackendClient(Settings(BACKEND_API_TOKEN="abc"))
    assert client._headers()["Authorization"] == "Bearer abc"
