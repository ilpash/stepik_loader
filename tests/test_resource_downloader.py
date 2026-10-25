import errno
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
    assert safe_filename("https://cdn.example.com/path/My%20File!.png") == "My_File_.png"


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
    mock_session_get.return_value = MockStreamResponse(200, chunks=[b"hello"], headers={"Content-Type": "text/plain"})
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-log-label", filename_hint="notes.txt")
    assert result == "notes.txt"
    assert (tmp_path / "notes.txt").read_bytes() == b"hello"
    mock_session_get.assert_called_once_with(
        "http://example.com/notes.txt", stream=True, timeout=resource_downloader.TIMEOUT_SECONDS
    )


def test_download_resource_guesses_extension_from_content_type_when_hint_has_no_suffix(tmp_path, mock_session_get):
    mock_session_get.return_value = MockStreamResponse(200, chunks=[b"video"], headers={"Content-Type": "video/mp4"})
    result = download_resource("http://example.com/video", tmp_path, "test-log-label", filename_hint="video")
    assert result == "video.mp4"


def test_download_resource_adds_no_extension_for_an_unknown_content_type(tmp_path, mock_session_get):
    mock_session_get.return_value = MockStreamResponse(200, headers={"Content-Type": "application/x-some-unknown-type"})
    result = download_resource("http://example.com/some_file", tmp_path, "test-log-label", filename_hint="some_file")
    assert result == "some_file"
    assert (tmp_path / "some_file").read_bytes() == b"data"


def test_download_resource_keeps_the_file_inside_the_folder(tmp_path, mock_session_get):
    step_dir = tmp_path / "step"
    step_dir.mkdir()
    mock_session_get.return_value = MockStreamResponse(200)
    result = download_resource("http://example.com/notes.txt", step_dir, "test-log-label", filename_hint="../notes.txt")
    assert result == "notes.txt"
    assert list(tmp_path.iterdir()) == [step_dir]
    assert list(step_dir.iterdir()) == [step_dir / "notes.txt"]


def test_download_resource_overwrites_a_file_from_an_earlier_run(tmp_path, mock_session_get):
    (tmp_path / "notes.txt").write_bytes(b"existing file")
    mock_session_get.return_value = MockStreamResponse(200, chunks=[b"new"])
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-log-label", filename_hint="notes.txt")
    assert result == "notes.txt"
    assert (tmp_path / "notes.txt").read_bytes() == b"new"


def test_download_resource_saves_nothing_when_the_server_sends_a_web_page(tmp_path, mock_session_get, caplog):
    mock_session_get.return_value = MockStreamResponse(200, headers={"Content-Type": "text/html; charset=utf-8"})
    page_url = "https://github.com/some_user/some_repo/blob/main/solution.py"
    result = download_resource(page_url, tmp_path, "test-log-label", filename_hint="solution.py")
    assert result is None
    assert list(tmp_path.iterdir()) == []
    assert f"WARNING [test-log-label] {page_url} returned a web page, keeping the link" in caplog.text


@pytest.mark.parametrize("status_code", [400, 404])
def test_download_resource_returns_none_on_non_retryable_http_error(status_code, tmp_path, mock_session_get, caplog):
    mock_session_get.return_value = MockStreamResponse(status_code)
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-log-label", filename_hint="notes.txt")
    assert result is None
    assert mock_session_get.call_count == 1
    assert list(tmp_path.iterdir()) == []
    assert (
        f"WARNING [test-log-label] failed to download http://example.com/notes.txt: HTTP {status_code}" in caplog.text
    )


def test_download_resource_retries_on_retryable_status_then_succeeds(tmp_path, mock_session_get, no_sleep):
    mock_session_get.side_effect = [MockStreamResponse(503), MockStreamResponse(200, chunks=[b"ok"])]
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-log-label", filename_hint="notes.txt")
    assert mock_session_get.call_count == 2
    assert result == "notes.txt"
    assert (tmp_path / "notes.txt").read_bytes() == b"ok"
    assert no_sleep.call_count == 1


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        ([MockStreamResponse(503)] * resource_downloader.MAX_ATTEMPTS, "HTTP 503 from http://example.com/notes.txt"),
        (requests.ConnectionError("connection refused"), "connection refused"),
    ],
)
def test_download_resource_returns_none_after_exhausting_retries(
    failure, reason, tmp_path, mock_session_get, no_sleep, caplog
):
    mock_session_get.side_effect = failure
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-log-label", filename_hint="notes.txt")
    assert result is None
    assert mock_session_get.call_count == resource_downloader.MAX_ATTEMPTS
    assert no_sleep.call_count == resource_downloader.MAX_ATTEMPTS - 1
    assert (
        f"WARNING [test-log-label] failed to download http://example.com/notes.txt "
        f"after {resource_downloader.MAX_ATTEMPTS} attempts: {reason}" in caplog.text
    )


def test_download_resource_removes_partial_file_when_stream_breaks(tmp_path, mock_session_get):
    class BrokenStreamResponse(MockStreamResponse):
        def iter_content(self, chunk_size):
            yield b"first half"
            raise requests.ConnectionError("stream dropped")

    mock_session_get.return_value = BrokenStreamResponse(200)
    result = download_resource("http://example.com/notes.txt", tmp_path, "test-log-label", filename_hint="notes.txt")
    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_download_resource_raises_on_the_first_failed_disk_write(tmp_path, mock_session_get):
    class UnwritableStreamResponse(MockStreamResponse):
        def iter_content(self, chunk_size):
            yield b"first half"
            raise OSError("no space left on device")

    mock_session_get.return_value = UnwritableStreamResponse(200)
    with pytest.raises(OSError, match="no space left on device"):
        download_resource("http://example.com/notes.txt", tmp_path, "test-log-label", filename_hint="notes.txt")
    assert mock_session_get.call_count == 1
    assert list(tmp_path.iterdir()) == []


def test_download_resource_raises_when_the_file_cannot_be_created(tmp_path, mock_session_get, monkeypatch):
    mock_session_get.return_value = MockStreamResponse(200)
    mock_open = MagicMock(side_effect=PermissionError(errno.EACCES, "Permission denied"))
    monkeypatch.setattr(resource_downloader, "open", mock_open, raising=False)
    with pytest.raises(PermissionError):
        download_resource("http://example.com/notes.txt", tmp_path, "test-log-label", filename_hint="notes.txt")
    assert mock_session_get.call_count == 1
    assert list(tmp_path.iterdir()) == []


def test_download_resource_removes_only_the_partial_file_when_interrupted(tmp_path, mock_session_get):
    class InterruptedStreamResponse(MockStreamResponse):
        def iter_content(self, chunk_size):
            yield b"first half"
            raise KeyboardInterrupt

    mock_session_get.side_effect = [MockStreamResponse(200, chunks=[b"whole file"]), InterruptedStreamResponse(200)]
    download_resource("http://example.com/first.txt", tmp_path, "test-log-label", filename_hint="first.txt")
    with pytest.raises(KeyboardInterrupt):
        download_resource("http://example.com/second.txt", tmp_path, "test-log-label", filename_hint="second.txt")
    assert list(tmp_path.iterdir()) == [tmp_path / "first.txt"]
    assert (tmp_path / "first.txt").read_bytes() == b"whole file"
