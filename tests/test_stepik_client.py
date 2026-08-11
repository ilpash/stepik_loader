import json
import time
from unittest.mock import MagicMock

import pytest
import requests

import stepik_client
from stepik_client import StepikAuthError, StepikClient


class MockResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    # Never let a real .env file on disk influence these tests.
    def mock_load_dotenv():
        pass

    monkeypatch.setattr(stepik_client, "load_dotenv", mock_load_dotenv)


@pytest.fixture
def fresh_client(tmp_path):
    """
    A client with valid credentials but no token fetched yet.
    """
    return StepikClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        token_cache_path=tmp_path / "cache.json",
    )


@pytest.fixture
def client(tmp_path):
    """
    A client that's already "authenticated", for _request/get/get_by_ids tests.
    """
    client = StepikClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        token_cache_path=tmp_path / "cache.json",
    )
    client._access_token = "test-token"
    client._token_expires_at = time.time() + 3600
    return client


# -- __init__ ------------------------------------------------------------------


def test_init_raises_stepik_auth_error_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("STEPIK_CLIENT_ID", raising=False)
    monkeypatch.delenv("STEPIK_CLIENT_SECRET", raising=False)
    with pytest.raises(StepikAuthError):
        StepikClient()


def test_init_reads_credentials_from_constructor_args(tmp_path):
    client = StepikClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        token_cache_path=tmp_path / "t.json",
    )
    assert client.client_id == "test-client-id"
    assert client.client_secret == "test-client-secret"


# -- _load_cached_token / _save_cached_token ------------------------------------


def test_load_cached_token_accepts_fresh_matching_cache(fresh_client):
    cache = {"client_id": "test-client-id", "access_token": "cached-token", "expires_at": time.time() + 3600}
    fresh_client.token_cache_path.write_text(json.dumps(cache))
    fresh_client._load_cached_token()
    assert fresh_client._access_token == "cached-token"


def test_load_cached_token_ignores_cache_for_different_client_id(fresh_client):
    cache = {"client_id": "other", "access_token": "cached-token", "expires_at": time.time() + 3600}
    fresh_client.token_cache_path.write_text(json.dumps(cache))
    fresh_client._load_cached_token()
    assert fresh_client._access_token is None


def test_load_cached_token_ignores_expired_cache(fresh_client):
    cache = {"client_id": "test-client-id", "access_token": "cached-token", "expires_at": time.time() - 100}
    fresh_client.token_cache_path.write_text(json.dumps(cache))
    fresh_client._load_cached_token()
    assert fresh_client._access_token is None


def test_load_cached_token_handles_missing_file(fresh_client):
    fresh_client._load_cached_token()
    assert fresh_client._access_token is None


def test_load_cached_token_handles_corrupt_json(fresh_client):
    fresh_client.token_cache_path.write_text("not json{{{")
    fresh_client._load_cached_token()
    assert fresh_client._access_token is None


def test_save_cached_token_writes_expected_json(fresh_client):
    fresh_client._access_token = "test-token"
    fresh_client._token_expires_at = 12345
    fresh_client._save_cached_token()
    data = json.loads(fresh_client.token_cache_path.read_text())
    assert data == {"client_id": "test-client-id", "access_token": "test-token", "expires_at": 12345}


# -- _fetch_new_token ------------------------------------------------------------


def test_fetch_new_token_success(fresh_client, monkeypatch):
    def mock_post(url, **kwargs):
        return MockResponse(200, json_data={"access_token": "fetched-token", "expires_in": 3600})

    monkeypatch.setattr(fresh_client.session, "post", mock_post)
    fresh_client._fetch_new_token()
    assert fresh_client._access_token == "fetched-token"
    assert fresh_client.token_cache_path.exists()


def test_fetch_new_token_raises_on_non_200(fresh_client, monkeypatch):
    def mock_post(url, **kwargs):
        return MockResponse(403, text="denied")

    monkeypatch.setattr(fresh_client.session, "post", mock_post)
    with pytest.raises(StepikAuthError):
        fresh_client._fetch_new_token()


def test_fetch_new_token_retries_on_retryable_status_then_succeeds(fresh_client, no_sleep, monkeypatch):
    responses = [MockResponse(503), MockResponse(200, json_data={"access_token": "fetched-token", "expires_in": 3600})]

    def mock_post(url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(fresh_client.session, "post", mock_post)
    fresh_client._fetch_new_token()
    assert fresh_client._access_token == "fetched-token"
    assert no_sleep.call_count == 1


def test_fetch_new_token_raises_after_exhausting_retries(fresh_client, no_sleep, monkeypatch):
    def mock_post(url, **kwargs):
        return MockResponse(503)

    monkeypatch.setattr(fresh_client.session, "post", mock_post)
    with pytest.raises(StepikAuthError):
        fresh_client._fetch_new_token()


# -- _request ---------------------------------------------------------------------


def test_request_returns_response_on_first_success(client, no_sleep, monkeypatch):
    mock_request = MagicMock(side_effect=lambda *a, **k: MockResponse(200))
    monkeypatch.setattr(client.session, "request", mock_request)
    result = client._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_request.call_count == 1
    assert no_sleep.call_count == 0


def test_request_retries_on_retryable_status_then_succeeds(client, no_sleep, monkeypatch):
    responses = [MockResponse(503), MockResponse(200)]

    def mock_request(method, url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(client.session, "request", mock_request)
    result = client._request("GET", "http://example.com")
    assert result.status_code == 200
    assert no_sleep.call_count == 1


def test_request_raises_after_exhausting_retries(client, no_sleep, monkeypatch):
    mock_request = MagicMock(side_effect=lambda *a, **k: MockResponse(503))
    monkeypatch.setattr(client.session, "request", mock_request)
    with pytest.raises(requests.HTTPError):
        client._request("GET", "http://example.com")
    assert mock_request.call_count == stepik_client.MAX_RETRIES


def test_request_refreshes_token_once_on_401_first_attempt(client, no_sleep, monkeypatch):
    responses = [MockResponse(401), MockResponse(200)]
    mock_request = MagicMock(side_effect=responses)

    def refresh_token():
        client._access_token = "new-token"

    mock_fetch_new_token = MagicMock(side_effect=refresh_token)

    monkeypatch.setattr(client.session, "request", mock_request)
    monkeypatch.setattr(client, "_fetch_new_token", mock_fetch_new_token)

    result = client._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_fetch_new_token.call_count == 1
    assert no_sleep.call_count == 0


def test_request_raises_on_non_retryable_status(client, no_sleep, monkeypatch):
    mock_request = MagicMock(side_effect=lambda *a, **k: MockResponse(404))
    monkeypatch.setattr(client.session, "request", mock_request)
    with pytest.raises(requests.HTTPError):
        client._request("GET", "http://example.com")
    assert mock_request.call_count == 1


# -- get / get_by_ids ---------------------------------------------------------------


def test_get_returns_parsed_json(client, monkeypatch):
    def mock_request(method, url, **kwargs):
        return MockResponse(200, json_data={"sample_key": "sample_value"})

    monkeypatch.setattr(client, "_request", mock_request)
    assert client.get("some/path") == {"sample_key": "sample_value"}


def test_get_builds_url_relative_to_api_base(client, monkeypatch):
    recorded = {}

    def mock_request(method, url, **kwargs):
        recorded["url"] = url
        return MockResponse(200, json_data={})

    monkeypatch.setattr(client, "_request", mock_request)
    client.get("some/path")
    assert recorded["url"] == stepik_client.API_BASE + "some/path"


def test_get_passes_through_an_already_absolute_url(client, monkeypatch):
    recorded = {}

    def mock_request(method, url, **kwargs):
        recorded["url"] = url
        return MockResponse(200, json_data={})

    monkeypatch.setattr(client, "_request", mock_request)
    client.get("https://stepik.org/media/a.txt")
    assert recorded["url"] == "https://stepik.org/media/a.txt"


def test_get_by_ids_batches_requests(client, monkeypatch):
    calls = []

    def mock_get(resource, params=None):
        calls.append(params)
        batch_ids = [int(v) for _, v in params]
        return {resource: [{"id": i} for i in batch_ids]}

    monkeypatch.setattr(client, "get", mock_get)
    ids = list(range(1, 66))
    results = client.get_by_ids("courses", ids, batch_size=30)

    assert [len(c) for c in calls] == [30, 30, 5]
    assert len(results) == 65


def test_get_by_ids_returns_empty_list_for_no_ids(client, monkeypatch):
    # Patched to guard against a regression making a real HTTP request.
    mock_get = MagicMock()
    monkeypatch.setattr(client, "get", mock_get)
    assert client.get_by_ids("courses", []) == []
    assert mock_get.call_count == 0
