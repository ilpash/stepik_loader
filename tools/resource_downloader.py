"""
Downloads a step's resources (video/image/audio/pdf/attachment) into that
step's own directory. Uses a session completely separate from the Stepik API
client, and only ever attaches the Stepik Authorization header when the
resource host is actually stepik.org -- third-party CDNs never see it.

A single resource failure is caught, logged as a warning tagged with the
calling context (course/lesson/step id), and reported as a miss (None) --
it never aborts the export.
"""
import logging
import mimetypes
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from stepik_client import STEPIK_AUTH_HOSTS

logger = logging.getLogger("stepik_export")

MAX_RETRIES = 5
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
CHUNK_SIZE = 64 * 1024

# This session never has a default Authorization header, unlike StepikClient's.
_download_session = requests.Session()


def safe_filename(url, fallback="resource"):
    name = unquote(Path(urlparse(url).path).name) or fallback
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[:150] or fallback


def _unique_dest(dest_dir, filename):
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 2
    while (dest_dir / f"{stem}_{i}{suffix}").exists():
        i += 1
    return dest_dir / f"{stem}_{i}{suffix}"


def download_resource(url, dest_dir, context, access_token=None, filename_hint=None):
    """
    Download `url` into `dest_dir`. Returns the local filename on success,
    or None on failure (a warning is logged in that case).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    host = urlparse(url).hostname or ""
    headers = {}
    if access_token and host in STEPIK_AUTH_HOSTS:
        headers["Authorization"] = f"Bearer {access_token}"

    dest_path = _unique_dest(dest_dir, filename_hint or safe_filename(url))

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with _download_session.get(url, headers=headers, stream=True, timeout=60) as response:
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = RuntimeError(f"HTTP {response.status_code}")
                elif response.status_code >= 400:
                    logger.warning(
                        "[%s] failed to download %s: HTTP %s", context, url, response.status_code
                    )
                    return None
                else:
                    if not dest_path.suffix:
                        ctype = response.headers.get("Content-Type", "").split(";")[0].strip()
                        ext = mimetypes.guess_extension(ctype) if ctype else None
                        if ext:
                            dest_path = dest_path.with_suffix(ext)
                    with open(dest_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                    print(f"  downloaded {dest_path.name}")
                    return dest_path.name
        except requests.RequestException as exc:
            last_error = exc

        if attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt)

    logger.warning(
        "[%s] failed to download %s after %d attempts: %s", context, url, MAX_RETRIES, last_error
    )
    return None
