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


@pytest.fixture
def client_without_token(tmp_path):
    return StepikClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        token_cache_path=tmp_path / "cache.json",
    )


@pytest.fixture
def client_with_token(tmp_path):
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


def test_load_cached_token_accepts_fresh_matching_cache(client_without_token):
    cache = {"client_id": "test-client-id", "access_token": "cached-token", "expires_at": time.time() + 3600}
    client_without_token.token_cache_path.write_text(json.dumps(cache))
    client_without_token._load_cached_token()
    assert client_without_token._access_token == "cached-token"


def test_load_cached_token_ignores_cache_for_different_client_id(client_without_token):
    cache = {"client_id": "other", "access_token": "cached-token", "expires_at": time.time() + 3600}
    client_without_token.token_cache_path.write_text(json.dumps(cache))
    client_without_token._load_cached_token()
    assert client_without_token._access_token is None


def test_load_cached_token_ignores_expired_cache(client_without_token):
    cache = {"client_id": "test-client-id", "access_token": "cached-token", "expires_at": time.time() - 100}
    client_without_token.token_cache_path.write_text(json.dumps(cache))
    client_without_token._load_cached_token()
    assert client_without_token._access_token is None


def test_load_cached_token_handles_missing_file(client_without_token):
    client_without_token._load_cached_token()
    assert client_without_token._access_token is None


def test_load_cached_token_handles_corrupt_json(client_without_token):
    client_without_token.token_cache_path.write_text("not json{{{")
    client_without_token._load_cached_token()
    assert client_without_token._access_token is None


def test_save_cached_token_writes_expected_json(client_without_token):
    client_without_token._access_token = "test-token"
    client_without_token._token_expires_at = 12345
    client_without_token._save_cached_token()
    data = json.loads(client_without_token.token_cache_path.read_text())
    assert data == {"client_id": "test-client-id", "access_token": "test-token", "expires_at": 12345}


# -- _ensure_token -----------------------------------------------------------------


def test_ensure_token_keeps_the_token_already_in_memory(client_with_token, monkeypatch):
    # The cache holds a different token, so reading it would be visible in the result.
    cache = {"client_id": "test-client-id", "access_token": "cached-token", "expires_at": time.time() + 3600}
    client_with_token.token_cache_path.write_text(json.dumps(cache))
    mock_fetch_new_token = MagicMock()
    monkeypatch.setattr(client_with_token, "_fetch_new_token", mock_fetch_new_token)

    client_with_token._ensure_token()

    assert client_with_token._access_token == "test-token"
    assert mock_fetch_new_token.call_count == 0


def test_ensure_token_falls_back_to_the_cache_when_memory_is_empty(client_without_token, monkeypatch):
    cache = {"client_id": "test-client-id", "access_token": "cached-token", "expires_at": time.time() + 3600}
    client_without_token.token_cache_path.write_text(json.dumps(cache))
    mock_fetch_new_token = MagicMock()
    monkeypatch.setattr(client_without_token, "_fetch_new_token", mock_fetch_new_token)

    client_without_token._ensure_token()

    assert client_without_token._access_token == "cached-token"
    assert mock_fetch_new_token.call_count == 0


def test_ensure_token_fetches_when_the_cache_is_expired(client_without_token, monkeypatch):
    cache = {"client_id": "test-client-id", "access_token": "cached-token", "expires_at": time.time() - 100}
    client_without_token.token_cache_path.write_text(json.dumps(cache))

    def fetch_token():
        client_without_token._access_token = "fetched-token"

    mock_fetch_new_token = MagicMock(side_effect=fetch_token)
    monkeypatch.setattr(client_without_token, "_fetch_new_token", mock_fetch_new_token)

    client_without_token._ensure_token()

    assert client_without_token._access_token == "fetched-token"
    assert mock_fetch_new_token.call_count == 1


def test_ensure_token_fetches_when_the_token_expires_within_the_margin(client_with_token, monkeypatch):
    client_with_token._token_expires_at = time.time() + stepik_client.TOKEN_EXPIRY_MARGIN_SECONDS - 1

    def fetch_token():
        client_with_token._access_token = "fetched-token"

    mock_fetch_new_token = MagicMock(side_effect=fetch_token)
    monkeypatch.setattr(client_with_token, "_fetch_new_token", mock_fetch_new_token)

    client_with_token._ensure_token()

    assert client_with_token._access_token == "fetched-token"
    assert mock_fetch_new_token.call_count == 1


# -- _fetch_new_token ------------------------------------------------------------


def test_fetch_new_token_success(client_without_token, monkeypatch):
    def mock_post(url, **kwargs):
        return MockResponse(200, json_data={"access_token": "fetched-token", "expires_in": 3600})

    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    client_without_token._fetch_new_token()
    assert client_without_token._access_token == "fetched-token"
    assert client_without_token.token_cache_path.exists()


def test_fetch_new_token_raises_on_non_200(client_without_token, monkeypatch):
    def mock_post(url, **kwargs):
        return MockResponse(403, text="denied")

    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    with pytest.raises(StepikAuthError):
        client_without_token._fetch_new_token()


def test_fetch_new_token_retries_on_retryable_status_then_succeeds(client_without_token, no_sleep, monkeypatch):
    responses = [MockResponse(503), MockResponse(200, json_data={"access_token": "fetched-token", "expires_in": 3600})]

    def mock_post(url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    client_without_token._fetch_new_token()
    assert client_without_token._access_token == "fetched-token"
    assert no_sleep.call_count == 1


def test_fetch_new_token_raises_after_exhausting_retries(client_without_token, no_sleep, monkeypatch):
    def mock_post(url, **kwargs):
        return MockResponse(503)

    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    with pytest.raises(StepikAuthError):
        client_without_token._fetch_new_token()
    assert no_sleep.call_count == stepik_client.MAX_RETRIES - 1


# -- _request ---------------------------------------------------------------------


def test_request_returns_response_on_first_success(client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(return_value=MockResponse(200))
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    result = client_with_token._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_request.call_count == 1
    assert no_sleep.call_count == 0


def test_request_retries_on_retryable_status_then_succeeds(client_with_token, no_sleep, monkeypatch):
    responses = [MockResponse(503), MockResponse(200)]

    def mock_request(method, url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    result = client_with_token._request("GET", "http://example.com")
    assert result.status_code == 200
    assert no_sleep.call_count == 1


def test_request_raises_after_exhausting_retries(client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(return_value=MockResponse(503))
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    with pytest.raises(requests.HTTPError):
        client_with_token._request("GET", "http://example.com")
    assert mock_request.call_count == stepik_client.MAX_RETRIES
    assert no_sleep.call_count == stepik_client.MAX_RETRIES - 1


def test_request_refreshes_token_once_on_401_first_attempt(client_with_token, no_sleep, monkeypatch):
    responses = [MockResponse(401), MockResponse(200)]
    mock_request = MagicMock(side_effect=responses)

    def refresh_token():
        client_with_token._access_token = "new-token"

    mock_fetch_new_token = MagicMock(side_effect=refresh_token)

    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    monkeypatch.setattr(client_with_token, "_fetch_new_token", mock_fetch_new_token)

    result = client_with_token._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_fetch_new_token.call_count == 1
    assert no_sleep.call_count == 0


def test_request_refreshes_token_on_401_after_a_retryable_failure(client_with_token, no_sleep, monkeypatch):
    responses = [MockResponse(503), MockResponse(401), MockResponse(200)]
    mock_request = MagicMock(side_effect=responses)

    def refresh_token():
        client_with_token._access_token = "new-token"

    mock_fetch_new_token = MagicMock(side_effect=refresh_token)

    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    monkeypatch.setattr(client_with_token, "_fetch_new_token", mock_fetch_new_token)

    result = client_with_token._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_fetch_new_token.call_count == 1
    assert no_sleep.call_count == 1


def test_request_raises_on_non_retryable_status(client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(return_value=MockResponse(404))
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    with pytest.raises(requests.HTTPError):
        client_with_token._request("GET", "http://example.com")
    assert mock_request.call_count == 1


# -- get / get_by_ids ---------------------------------------------------------------


def test_get_returns_parsed_json(client_with_token, monkeypatch):
    def mock_request(method, url, **kwargs):
        return MockResponse(200, json_data={"sample_key": "sample_value"})

    monkeypatch.setattr(client_with_token, "_request", mock_request)
    assert client_with_token.get("some/path") == {"sample_key": "sample_value"}


def test_get_builds_url_relative_to_api_base(client_with_token, monkeypatch):
    recorded = {}

    def mock_request(method, url, **kwargs):
        recorded["url"] = url
        return MockResponse(200, json_data={})

    monkeypatch.setattr(client_with_token, "_request", mock_request)
    client_with_token.get("some/path")
    assert recorded["url"] == stepik_client.API_BASE + "some/path"


def test_get_passes_through_an_already_absolute_url(client_with_token, monkeypatch):
    recorded = {}

    def mock_request(method, url, **kwargs):
        recorded["url"] = url
        return MockResponse(200, json_data={})

    monkeypatch.setattr(client_with_token, "_request", mock_request)
    client_with_token.get("https://stepik.org/media/a.txt")
    assert recorded["url"] == "https://stepik.org/media/a.txt"


def test_get_by_ids_batches_requests(client_with_token, monkeypatch):
    calls = []

    def mock_get(resource, params=None):
        calls.append(params)
        batch_ids = [int(value) for _, value in params]
        return {resource: [{"id": batch_id} for batch_id in batch_ids]}

    monkeypatch.setattr(client_with_token, "get", mock_get)
    ids = list(range(1, 66))
    results = client_with_token.get_by_ids("courses", ids, batch_size=30)

    assert [len(batch) for batch in calls] == [30, 30, 5]
    assert len(results) == 65


def test_get_by_ids_returns_empty_list_for_no_ids(client_with_token, monkeypatch):
    mock_get = MagicMock()
    monkeypatch.setattr(client_with_token, "get", mock_get)
    assert client_with_token.get_by_ids("courses", []) == []
    assert mock_get.call_count == 0
