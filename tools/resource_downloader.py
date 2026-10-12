"""
Downloads a step's resources (video/image/audio/pdf/attachment) into that
step's own directory. Uses a session completely separate from the Stepik API
client, and only ever attaches the Stepik Authorization header when the
resource host is actually stepik.org -- third-party CDNs never see it.

A failed download, or a server answering with a web page instead of a file,
is logged as a warning tagged with the log label (course/lesson/step id) and
reported as a miss (None). An error writing the file to disk is raised to the
caller instead.
"""

import logging
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from retry import MAX_ATTEMPTS, RETRYABLE_STATUS_CODES, backoff_sleep

logger = logging.getLogger("stepik_export")

CHUNK_SIZE = 64 * 1024

MAX_FILENAME_STEM_LEN = 100
MAX_FILENAME_SUFFIX_LEN = 10

# Hosts that are allowed to receive the Stepik Authorization header.
# Resource downloads (video/image/attachment CDNs) must never send it
# to anything outside this set.
STEPIK_AUTH_HOSTS = {"stepik.org", "www.stepik.org"}

BUILTIN_MIME_TYPES = mimetypes.MimeTypes()

# This session never has a default Authorization header, unlike StepikClient's.
_download_session = requests.Session()


def safe_filename(url):
    name = unquote(Path(urlparse(url).path).name) or "resource"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    stem, suffix = Path(name).stem, Path(name).suffix
    return stem[:MAX_FILENAME_STEM_LEN] + suffix[:MAX_FILENAME_SUFFIX_LEN]


def _name_from_content_type(filename, content_type):
    if Path(filename).suffix:
        return filename
    extension = BUILTIN_MIME_TYPES.guess_extension(content_type) if content_type else None
    return filename + extension if extension else filename


def _write_stream(response, dest_path):
    try:
        with open(dest_path, "wb") as destination:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    destination.write(chunk)
    except OSError:
        # Don't leave a truncated file behind for this attempt.
        dest_path.unlink(missing_ok=True)
        raise


def download_resource(url, dest_dir, log_label, access_token=None, filename_hint=None):
    """
    Returns the local filename, or None if the download failed (logged as a warning).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    host = urlparse(url).hostname or ""
    headers = {}
    if access_token and host in STEPIK_AUTH_HOSTS:
        headers["Authorization"] = f"Bearer {access_token}"

    # safe_filename() also sanitizes a caller-supplied hint (basename-only,
    # whitelisted characters), so a hint can never escape dest_dir.
    filename = safe_filename(filename_hint or url)

    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with _download_session.get(url, headers=headers, stream=True, timeout=60) as response:
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = RuntimeError(f"HTTP {response.status_code}")
                elif response.status_code >= 400:
                    logger.warning("[%s] failed to download %s: HTTP %s", log_label, url, response.status_code)
                    return None
                else:
                    content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
                    if content_type == "text/html":
                        logger.warning("[%s] %s returned a web page, keeping the link", log_label, url)
                        return None
                    dest_path = dest_dir / _name_from_content_type(filename, content_type)
                    _write_stream(response, dest_path)
                    logger.info("  downloaded %s", dest_path.name)
                    return dest_path.name
        except requests.RequestException as exc:
            last_error = exc

        backoff_sleep(attempt)

    logger.warning("[%s] failed to download %s after %d attempts: %s", log_label, url, MAX_ATTEMPTS, last_error)
    return None
