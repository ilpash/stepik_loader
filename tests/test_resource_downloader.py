from unittest.mock import MagicMock

import pytest
import requests

import resource_downloader
from resource_downloader import MAX_FILENAME_STEM_LEN, MAX_FILENAME_SUFFIX_LEN, download_resource, safe_filename


class MockStreamResponse:
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


@pytest.fixture
def mock_session_get(monkeypatch):
    mock_get = MagicMock()
    monkeypatch.setattr(resource_downloader._download_session, "get", mock_get)
    return mock_get


# -- safe_filename -------------------------------------------------------------


def test_safe_filename_basic_case():
    assert safe_filename("https://cdn.example.com/path/My File!.png") == "My_File_.png"


def test_safe_filename_falls_back_when_url_has_no_basename():
    assert safe_filename("https://cdn.example.com/") == "resource"


def test_safe_filename_truncates_the_stem_but_keeps_the_extension():
    long_name = "a" * 300 + ".png"
    result = safe_filename(f"https://cdn.example.com/{long_name}")
    assert result == "a" * MAX_FILENAME_STEM_LEN + ".png"


def test_safe_filename_truncates_an_unusually_long_extension_too():
    long_name = "a" * 300 + "." + "b" * 300
    result = safe_filename(f"https://cdn.example.com/{long_name}")
    assert result == "a" * MAX_FILENAME_STEM_LEN + "." + "b" * (MAX_FILENAME_SUFFIX_LEN - 1)


# -- download_resource ---------------------------------------------------------


def test_download_resource_basic_case(tmp_path, mock_session_get):
    mock_session_get.return_value = MockStreamResponse(200, chunks=[b"hello"])
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-context")
    assert result == "notes.txt"
    assert (tmp_path / "notes.txt").read_bytes() == b"hello"


def test_download_resource_attaches_auth_header_for_stepik_host(tmp_path, mock_session_get):
    mock_session_get.return_value = MockStreamResponse(200)
    download_resource("https://stepik.org/media/notes.txt", tmp_path, "test-context", access_token="test-token")
    assert mock_session_get.call_args.kwargs["headers"].get("Authorization") == "Bearer test-token"


def test_download_resource_omits_auth_header_for_non_stepik_host(tmp_path, mock_session_get):
    mock_session_get.return_value = MockStreamResponse(200)
    download_resource("https://example.com/notes.txt", tmp_path, "test-context", access_token="test-token")
    assert "Authorization" not in mock_session_get.call_args.kwargs["headers"]


def test_download_resource_guesses_extension_from_content_type_when_hint_has_no_suffix(tmp_path, mock_session_get):
    mock_session_get.return_value = MockStreamResponse(200, chunks=[b"x"], headers={"Content-Type": "video/mp4"})
    result = download_resource("http://example.com/video", tmp_path, "test-context", filename_hint="video")
    assert result == "video.mp4"


def test_download_resource_overwrites_a_file_from_an_earlier_run(tmp_path, mock_session_get):
    # The hint has no extension, so it becomes "video.mp4", which this directory already has.
    (tmp_path / "video.mp4").write_bytes(b"existing file")
    mock_session_get.return_value = MockStreamResponse(200, chunks=[b"new"], headers={"Content-Type": "video/mp4"})
    result = download_resource("http://example.com/video", tmp_path, "test-context", filename_hint="video")
    assert result == "video.mp4"
    assert (tmp_path / "video.mp4").read_bytes() == b"new"


def test_download_resource_saves_nothing_when_the_server_sends_a_web_page(tmp_path, mock_session_get, caplog):
    mock_session_get.return_value = MockStreamResponse(200, headers={"Content-Type": "text/html; charset=utf-8"})
    result = download_resource("https://github.com/some_user/some_repo/blob/main/solution.py", tmp_path, "test-context")
    assert result is None
    assert list(tmp_path.iterdir()) == []
    assert "returned a web page" in caplog.text


def test_download_resource_returns_none_on_non_retryable_http_error(tmp_path, mock_session_get):
    mock_session_get.return_value = MockStreamResponse(404)
    result = download_resource("http://example.com/missing.txt", tmp_path, "test-context")
    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_download_resource_retries_on_retryable_status_then_succeeds(tmp_path, mock_session_get, no_sleep):
    mock_session_get.side_effect = [MockStreamResponse(503), MockStreamResponse(200, chunks=[b"ok"])]
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-context")
    assert mock_session_get.call_count == 2
    assert result == "notes.txt"
    assert (tmp_path / "notes.txt").read_bytes() == b"ok"
    assert no_sleep.call_count == 1


def test_download_resource_returns_none_after_exhausting_retries(tmp_path, mock_session_get, no_sleep):
    mock_session_get.return_value = MockStreamResponse(503)
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-context")
    assert result is None
    assert mock_session_get.call_count == resource_downloader.MAX_ATTEMPTS
    assert no_sleep.call_count == resource_downloader.MAX_ATTEMPTS - 1


def test_download_resource_removes_partial_file_when_stream_breaks(tmp_path, mock_session_get, no_sleep):
    class BrokenStreamResponse(MockStreamResponse):
        def iter_content(self, chunk_size):
            yield b"first half"
            raise requests.ConnectionError("stream dropped")

    mock_session_get.return_value = BrokenStreamResponse(200)
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-context")
    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_download_resource_raises_on_the_first_failed_disk_write(tmp_path, mock_session_get):
    class UnwritableStreamResponse(MockStreamResponse):
        def iter_content(self, chunk_size):
            yield b"first half"
            raise OSError("no space left on device")

    mock_session_get.return_value = UnwritableStreamResponse(200)
    with pytest.raises(OSError, match="no space left on device"):
        download_resource("http://example.com/notes.txt", tmp_path, "test-context")
    assert mock_session_get.call_count == 1
    assert list(tmp_path.iterdir()) == []


def test_download_resource_removes_partial_file_when_interrupted(tmp_path, mock_session_get):
    class InterruptedStreamResponse(MockStreamResponse):
        def iter_content(self, chunk_size):
            yield b"first half"
            raise KeyboardInterrupt

    mock_session_get.return_value = InterruptedStreamResponse(200)
    with pytest.raises(KeyboardInterrupt):
        download_resource("http://example.com/notes.txt", tmp_path, "test-context")
    assert list(tmp_path.iterdir()) == []


def test_download_resource_returns_none_on_connection_error(tmp_path, mock_session_get, no_sleep):
    mock_session_get.side_effect = requests.ConnectionError("connection refused")
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-context")
    assert result is None
