"""
Shared retry/backoff constants for HTTP calls against Stepik's API and its
resource CDNs, used by both stepik_client.py and resource_downloader.py.
"""

import time

MAX_ATTEMPTS = 5
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def backoff_sleep(attempt):
    """
    Doubles the wait per attempt, and skips it after the last one.
    """
    if attempt < MAX_ATTEMPTS - 1:
        time.sleep(2**attempt)
