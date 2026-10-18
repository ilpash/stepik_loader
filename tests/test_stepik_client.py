import json
import time
from unittest.mock import MagicMock, call

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
def client_with_token(client_without_token):
    client = client_without_token
    client._access_token = "test-token"
    client._token_expires_at = time.time() + 3600
    return client


# -- __init__ ------------------------------------------------------------------


@pytest.mark.parametrize("missing_variable", ["STEPIK_CLIENT_ID", "STEPIK_CLIENT_SECRET"])
def test_init_raises_stepik_auth_error_when_a_credential_is_missing(missing_variable, monkeypatch):
    monkeypatch.setenv("STEPIK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("STEPIK_CLIENT_SECRET", "test-client-secret")
    monkeypatch.delenv(missing_variable)
    with pytest.raises(StepikAuthError):
        StepikClient()


def test_init_reads_every_constructor_arg(tmp_path):
    client = StepikClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        token_cache_path=tmp_path / "cache.json",
    )
    assert client.client_id == "test-client-id"
    assert client.client_secret == "test-client-secret"
    assert client.token_cache_path == tmp_path / "cache.json"


def test_init_reads_credentials_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("STEPIK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("STEPIK_CLIENT_SECRET", "test-client-secret")
    client = StepikClient(token_cache_path=tmp_path / "cache.json")
    assert client.client_id == "test-client-id"
    assert client.client_secret == "test-client-secret"


def test_init_uses_the_default_token_cache(temporary_token_cache):
    client = StepikClient(client_id="test-client-id", client_secret="test-client-secret")
    assert client.token_cache_path == temporary_token_cache


# -- _load_cached_token / _save_cached_token -----------------------------------


def test_load_cached_token_basic_case(client_without_token):
    cache = {"client_id": "test-client-id", "access_token": "cached-token", "expires_at": time.time() + 3600}
    client_without_token.token_cache_path.write_text(json.dumps(cache))
    client_without_token._load_cached_token()
    assert client_without_token._access_token == "cached-token"
    assert client_without_token._token_expires_at == cache["expires_at"]


def test_load_cached_token_ignores_cache_for_different_client_id(client_without_token):
    cache = {"client_id": "other-client-id", "access_token": "cached-token", "expires_at": time.time() + 3600}
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


def test_save_cached_token_basic_case(client_without_token):
    client_without_token._access_token = "test-token"
    client_without_token._token_expires_at = 12345
    client_without_token._save_cached_token()
    data = json.loads(client_without_token.token_cache_path.read_text())
    assert data == {"client_id": "test-client-id", "access_token": "test-token", "expires_at": 12345}


# -- _ensure_token / access_token ----------------------------------------------


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


def test_access_token_refreshes_an_expired_token(client_with_token, monkeypatch):
    client_with_token._token_expires_at = time.time() - 1

    def fetch_token():
        client_with_token._access_token = "fetched-token"

    mock_fetch_new_token = MagicMock(side_effect=fetch_token)
    monkeypatch.setattr(client_with_token, "_fetch_new_token", mock_fetch_new_token)

    assert client_with_token.access_token == "fetched-token"
    assert mock_fetch_new_token.call_count == 1


# -- _fetch_new_token ----------------------------------------------------------


def test_fetch_new_token_basic_case(client_without_token, monkeypatch):
    mock_post = MagicMock(
        return_value=MockResponse(200, json_data={"access_token": "fetched-token", "expires_in": 36000})
    )
    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    before = time.time()
    client_without_token._fetch_new_token()
    assert client_without_token._access_token == "fetched-token"
    assert before + 36000 <= client_without_token._token_expires_at <= time.time() + 36000
    mock_post.assert_called_once_with(
        stepik_client.AUTH_URL,
        data={"grant_type": "client_credentials"},
        auth=("test-client-id", "test-client-secret"),
        timeout=stepik_client.TIMEOUT_SECONDS,
    )
    data = json.loads(client_without_token.token_cache_path.read_text())
    assert data == {
        "client_id": "test-client-id",
        "access_token": "fetched-token",
        "expires_at": client_without_token._token_expires_at,
    }


def test_fetch_new_token_raises_on_non_retryable_status(client_without_token, monkeypatch):
    def mock_post(url, **kwargs):
        return MockResponse(403, text="shown " * 50 + "cut " * 100)

    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    with pytest.raises(StepikAuthError) as exc_info:
        client_without_token._fetch_new_token()
    assert str(exc_info.value) == "Failed to obtain Stepik access token (HTTP 403): " + "shown " * 50


def test_fetch_new_token_retries_on_retryable_status_then_succeeds(client_without_token, no_sleep, monkeypatch):
    mock_post = MagicMock(
        side_effect=[
            MockResponse(503),
            MockResponse(200, json_data={"access_token": "fetched-token", "expires_in": 3600}),
        ]
    )
    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    client_without_token._fetch_new_token()
    assert client_without_token._access_token == "fetched-token"
    assert mock_post.call_count == 2
    assert no_sleep.call_count == 1


def test_fetch_new_token_retries_after_a_connection_error(client_without_token, no_sleep, monkeypatch):
    mock_post = MagicMock(
        side_effect=[
            requests.ConnectionError("connection refused"),
            MockResponse(200, json_data={"access_token": "fetched-token", "expires_in": 3600}),
        ]
    )
    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    client_without_token._fetch_new_token()
    assert client_without_token._access_token == "fetched-token"
    assert mock_post.call_count == 2
    assert no_sleep.call_count == 1


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        ([MockResponse(503)] * stepik_client.MAX_ATTEMPTS, f"HTTP 503 from {stepik_client.AUTH_URL}"),
        (requests.ConnectionError("connection refused"), "connection refused"),
    ],
)
def test_fetch_new_token_raises_after_exhausting_retries(failure, reason, client_without_token, no_sleep, monkeypatch):
    mock_post = MagicMock(side_effect=failure)
    monkeypatch.setattr(client_without_token.session, "post", mock_post)
    with pytest.raises(StepikAuthError) as exc_info:
        client_without_token._fetch_new_token()
    assert str(exc_info.value) == (
        f"Failed to obtain Stepik access token after {stepik_client.MAX_ATTEMPTS} attempts: {reason}"
    )
    assert mock_post.call_count == stepik_client.MAX_ATTEMPTS
    assert no_sleep.call_count == stepik_client.MAX_ATTEMPTS - 1


# -- _request ------------------------------------------------------------------


def test_request_basic_case(client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(return_value=MockResponse(200))
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    result = client_with_token._request("GET", "http://example.com", params=[("ids[]", 1)])
    assert result.status_code == 200
    mock_request.assert_called_once_with(
        "GET",
        "http://example.com",
        headers={"Authorization": "Bearer test-token"},
        timeout=stepik_client.TIMEOUT_SECONDS,
        params=[("ids[]", 1)],
    )
    assert no_sleep.call_count == 0


def test_request_retries_on_retryable_status_then_succeeds(client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(side_effect=[MockResponse(503), MockResponse(200)])
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    result = client_with_token._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_request.call_count == 2
    assert no_sleep.call_count == 1


def test_request_retries_after_a_connection_error(client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(side_effect=[requests.ConnectionError("connection refused"), MockResponse(200)])
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    result = client_with_token._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_request.call_count == 2
    assert no_sleep.call_count == 1


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        ([MockResponse(503)] * stepik_client.MAX_ATTEMPTS, "HTTP 503 from http://example.com"),
        (requests.ConnectionError("connection refused"), "connection refused"),
    ],
)
def test_request_raises_after_exhausting_retries(failure, reason, client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(side_effect=failure)
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    with pytest.raises(requests.RequestException) as exc_info:
        client_with_token._request("GET", "http://example.com")
    assert str(exc_info.value) == reason
    assert mock_request.call_count == stepik_client.MAX_ATTEMPTS
    assert no_sleep.call_args_list == [call(1), call(2), call(4), call(8)]


def test_request_refreshes_token_once_on_401_first_attempt(client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(side_effect=[MockResponse(401), MockResponse(200)])

    def refresh_token():
        client_with_token._access_token = "new-token"

    mock_fetch_new_token = MagicMock(side_effect=refresh_token)

    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    monkeypatch.setattr(client_with_token, "_fetch_new_token", mock_fetch_new_token)

    result = client_with_token._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_fetch_new_token.call_count == 1
    assert mock_request.call_args.kwargs["headers"]["Authorization"] == "Bearer new-token"
    assert no_sleep.call_count == 0


def test_request_refreshes_token_on_401_after_a_retryable_failure(client_with_token, no_sleep, monkeypatch):
    mock_request = MagicMock(side_effect=[MockResponse(503), MockResponse(401), MockResponse(200)])

    def refresh_token():
        client_with_token._access_token = "new-token"

    mock_fetch_new_token = MagicMock(side_effect=refresh_token)

    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    monkeypatch.setattr(client_with_token, "_fetch_new_token", mock_fetch_new_token)

    result = client_with_token._request("GET", "http://example.com")
    assert result.status_code == 200
    assert mock_fetch_new_token.call_count == 1
    assert mock_request.call_args.kwargs["headers"]["Authorization"] == "Bearer new-token"
    assert no_sleep.call_count == 1


def test_request_raises_when_the_refreshed_token_is_rejected(client_with_token, monkeypatch):
    mock_request = MagicMock(return_value=MockResponse(401))
    mock_fetch_new_token = MagicMock()
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    monkeypatch.setattr(client_with_token, "_fetch_new_token", mock_fetch_new_token)

    with pytest.raises(requests.HTTPError):
        client_with_token._request("GET", "http://example.com")
    assert mock_fetch_new_token.call_count == 1
    assert mock_request.call_count == 2


def test_request_raises_on_non_retryable_status(client_with_token, monkeypatch):
    mock_request = MagicMock(return_value=MockResponse(404))
    monkeypatch.setattr(client_with_token.session, "request", mock_request)
    with pytest.raises(requests.HTTPError):
        client_with_token._request("GET", "http://example.com")
    assert mock_request.call_count == 1


# -- get / get_by_ids ----------------------------------------------------------


def test_get_basic_case(client_with_token, monkeypatch):
    mock_request = MagicMock(return_value=MockResponse(200, json_data={"sample_key": "sample_value"}))
    monkeypatch.setattr(client_with_token, "_request", mock_request)

    assert client_with_token.get("some/path", params=[("ids[]", "1")]) == {"sample_key": "sample_value"}
    mock_request.assert_called_once_with("GET", stepik_client.API_BASE + "some/path", params=[("ids[]", "1")])


def test_get_by_ids_batches_requests(client_with_token, monkeypatch):
    mock_get = MagicMock(
        side_effect=[
            {"courses": [{"id": course_id} for course_id in range(1, 31)]},
            {"courses": [{"id": course_id} for course_id in range(31, 61)]},
            {"courses": [{"id": course_id} for course_id in range(61, 66)]},
        ]
    )
    monkeypatch.setattr(client_with_token, "get", mock_get)

    results = client_with_token.get_by_ids("courses", list(range(1, 66)))

    assert mock_get.call_args_list == [
        call("courses", params=[("ids[]", course_id) for course_id in range(1, 31)]),
        call("courses", params=[("ids[]", course_id) for course_id in range(31, 61)]),
        call("courses", params=[("ids[]", course_id) for course_id in range(61, 66)]),
    ]
    assert len(results) == 65


def test_get_by_ids_returns_empty_list_for_no_ids(client_with_token, monkeypatch):
    mock_get = MagicMock()
    monkeypatch.setattr(client_with_token, "get", mock_get)
    assert client_with_token.get_by_ids("courses", []) == []
    assert mock_get.call_count == 0
