"""
Shared retry/backoff constants for HTTP calls against Stepik's API and its
resource CDNs, used by both stepik_client.py and resource_downloader.py.
"""

import time

MAX_RETRIES = 5
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def backoff_sleep(attempt):
    """
    Sleep the exponential-backoff delay for a failed `attempt` (0-based),
    unless it was the last attempt.
    """
    if attempt < MAX_RETRIES - 1:
        time.sleep(2**attempt)
