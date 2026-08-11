import requests

import resource_downloader
from resource_downloader import safe_filename, _unique_dest, download_resource


class MockStreamResponse:
    """
    Mimics a requests.Response used as a context manager with stream=True.
    """

    def __init__(self, status_code, chunks=(b"data",), headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, chunk_size):
        yield from self._chunks


# -- safe_filename ---------------------------------------------------------------

def test_safe_filename_sanitizes_and_uses_basename():
    assert safe_filename("https://x.com/path/My File!.png") == "My_File_.png"


def test_safe_filename_falls_back_when_url_has_no_basename():
    assert safe_filename("https://x.com/") == "resource"


def test_safe_filename_truncates_to_150_chars():
    long_name = "a" * 300 + ".png"
    result = safe_filename(f"https://x.com/{long_name}")
    assert len(result) <= 150


# -- _unique_dest ------------------------------------------------------------------

def test_unique_dest_returns_plain_path_when_no_collision(tmp_path):
    assert _unique_dest(tmp_path, "a.txt") == tmp_path / "a.txt"


def test_unique_dest_appends_suffix_on_collision(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert _unique_dest(tmp_path, "a.txt") == tmp_path / "a_2.txt"


def test_unique_dest_increments_past_multiple_collisions(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "a_2.txt").write_text("x")
    assert _unique_dest(tmp_path, "a.txt") == tmp_path / "a_3.txt"


# -- download_resource ---------------------------------------------------------------

def test_download_resource_success_writes_file_and_returns_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(
        resource_downloader._download_session, "get",
        lambda url, headers=None, stream=None, timeout=None: MockStreamResponse(200, chunks=[b"hello"]),
    )
    result = download_resource("http://example.com/a.txt", tmp_path, "test-context")
    assert result == "a.txt"
    assert (tmp_path / "a.txt").read_bytes() == b"hello"


def test_download_resource_attaches_auth_header_for_stepik_host(tmp_path, monkeypatch):
    recorded = {}

    def mock_get(url, headers=None, stream=None, timeout=None):
        recorded["headers"] = headers
        return MockStreamResponse(200)

    monkeypatch.setattr(resource_downloader._download_session, "get", mock_get)
    download_resource("https://stepik.org/media/a.txt", tmp_path, "test-context", access_token="test-token")
    assert recorded["headers"].get("Authorization") == "Bearer test-token"


def test_download_resource_omits_auth_header_for_non_stepik_host(tmp_path, monkeypatch):
    recorded = {}

    def mock_get(url, headers=None, stream=None, timeout=None):
        recorded["headers"] = headers
        return MockStreamResponse(200)

    monkeypatch.setattr(resource_downloader._download_session, "get", mock_get)
    download_resource("https://example.com/a.txt", tmp_path, "test-context", access_token="test-token")
    assert "Authorization" not in recorded["headers"]


def test_download_resource_guesses_extension_from_content_type_when_hint_has_no_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(
        resource_downloader._download_session, "get",
        lambda url, headers=None, stream=None, timeout=None: MockStreamResponse(
            200, chunks=[b"x"], headers={"Content-Type": "video/mp4"}
        ),
    )
    result = download_resource("http://example.com/video", tmp_path, "test-context", filename_hint="video")
    assert result.endswith(".mp4")


def test_download_resource_returns_none_on_non_retryable_http_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        resource_downloader._download_session, "get",
        lambda url, headers=None, stream=None, timeout=None: MockStreamResponse(404),
    )
    result = download_resource("http://example.com/missing.txt", tmp_path, "test-context")
    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_download_resource_retries_on_retryable_status_then_succeeds(tmp_path, monkeypatch, no_sleep):
    responses = [MockStreamResponse(503), MockStreamResponse(200, chunks=[b"ok"])]
    calls = []

    def mock_get(url, headers=None, stream=None, timeout=None):
        calls.append(1)
        return responses.pop(0)

    monkeypatch.setattr(resource_downloader._download_session, "get", mock_get)
    result = download_resource("http://example.com/a.txt", tmp_path, "test-context")
    assert len(calls) == 2
    assert result == "a.txt"
    assert (tmp_path / "a.txt").read_bytes() == b"ok"
    assert no_sleep.call_count == 1


def test_download_resource_returns_none_after_exhausting_retries(tmp_path, monkeypatch, no_sleep):
    calls = []

    def mock_get(url, headers=None, stream=None, timeout=None):
        calls.append(1)
        return MockStreamResponse(503)

    monkeypatch.setattr(resource_downloader._download_session, "get", mock_get)
    result = download_resource("http://example.com/a.txt", tmp_path, "test-context")
    assert result is None
    assert len(calls) == resource_downloader.MAX_RETRIES


def test_download_resource_returns_none_on_connection_error(tmp_path, monkeypatch, no_sleep):
    def mock_get(url, headers=None, stream=None, timeout=None):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(resource_downloader._download_session, "get", mock_get)
    result = download_resource("http://example.com/a.txt", tmp_path, "test-context")
    assert result is None
