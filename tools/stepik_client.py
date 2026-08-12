"""
Authenticated access to the Stepik REST API.

Handles OAuth2 client_credentials auth (public content only), on-disk token
caching, batched ids[] lookups, and a small hand-rolled retry/backoff loop
for transient failures (429 / 5xx / connection errors).
"""

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from retry import MAX_RETRIES, RETRYABLE_STATUS_CODES, backoff_sleep

API_BASE = "https://stepik.org/api/"
AUTH_URL = "https://stepik.org/oauth2/token/"

# Hosts that are allowed to receive the Stepik Authorization header.
# Resource downloads (video/image/attachment CDNs) must never send it
# to anything outside this set.
STEPIK_AUTH_HOSTS = {"stepik.org", "www.stepik.org"}

DEFAULT_TOKEN_CACHE = Path(__file__).resolve().parent.parent / "stepik_token.json"


class StepikAuthError(RuntimeError):
    pass


class StepikClient:
    def __init__(self, client_id=None, client_secret=None, token_cache_path=None):
        load_dotenv()
        self.client_id = client_id or os.environ.get("STEPIK_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("STEPIK_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise StepikAuthError(
                "STEPIK_CLIENT_ID / STEPIK_CLIENT_SECRET are not set. "
                "Copy .env.example to .env and fill in your OAuth2 app credentials "
                "from https://stepik.org/oauth2/applications/."
            )
        self.token_cache_path = Path(token_cache_path or DEFAULT_TOKEN_CACHE)
        self._access_token = None
        self._token_expires_at = 0
        self.session = requests.Session()

    # -- auth -----------------------------------------------------------

    def _load_cached_token(self):
        if not self.token_cache_path.exists():
            return
        try:
            data = json.loads(self.token_cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        if data.get("client_id") != self.client_id:
            return
        if data.get("expires_at", 0) > time.time() + 30:
            self._access_token = data["access_token"]
            self._token_expires_at = data["expires_at"]

    def _save_cached_token(self):
        self.token_cache_path.write_text(
            json.dumps(
                {
                    "client_id": self.client_id,
                    "access_token": self._access_token,
                    "expires_at": self._token_expires_at,
                }
            )
        )

    def _fetch_new_token(self):
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.post(
                    AUTH_URL,
                    data={"grant_type": "client_credentials"},
                    auth=(self.client_id, self.client_secret),
                    timeout=30,
                )
            except requests.RequestException as exc:
                last_error = exc
                backoff_sleep(attempt)
                continue

            if response.status_code in RETRYABLE_STATUS_CODES:
                last_error = StepikAuthError(f"HTTP {response.status_code} from {AUTH_URL}")
                backoff_sleep(attempt)
                continue
            if response.status_code != 200:
                raise StepikAuthError(
                    f"Failed to obtain Stepik access token (HTTP {response.status_code}): {response.text[:300]}"
                )

            payload = response.json()
            self._access_token = payload["access_token"]
            self._token_expires_at = time.time() + payload.get("expires_in", 3600)
            self._save_cached_token()
            return

        raise StepikAuthError(f"Failed to obtain Stepik access token after {MAX_RETRIES} attempts: {last_error}")

    def _ensure_token(self):
        if self._access_token and self._token_expires_at > time.time() + 30:
            return
        self._load_cached_token()
        if self._access_token and self._token_expires_at > time.time() + 30:
            return
        self._fetch_new_token()

    @property
    def access_token(self):
        self._ensure_token()
        return self._access_token

    # -- requests ---------------------------------------------------------

    def _request(self, method, url, **kwargs):
        self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(method, url, headers=headers, timeout=60, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
            else:
                if response.status_code == 401 and attempt == 0:
                    # Token might have just been invalidated server-side; force refresh once.
                    self._fetch_new_token()
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    continue
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    response.raise_for_status()
                    return response
                last_error = requests.HTTPError(f"HTTP {response.status_code} from {url}")

            backoff_sleep(attempt)

        raise last_error or StepikAuthError(f"Request to {url} failed after {MAX_RETRIES} attempts")

    def get(self, path, params=None):
        """
        GET a single API path (relative to API_BASE) and return the parsed JSON body.
        """
        url = path if path.startswith("http") else API_BASE + path.lstrip("/")
        response = self._request("GET", url, params=params)
        return response.json()

    def get_by_ids(self, resource, ids, batch_size=30):
        """
        Fetch a list of objects for `resource` (e.g. 'courses', 'lessons', 'steps')
        by id, batching requests to avoid oversized query strings. Returns a flat
        list of the objects, in no guaranteed order.
        """
        ids = list(ids)
        results = []
        for i in range(0, len(ids), batch_size):
            batch = ids[i : i + batch_size]
            params = [("ids[]", str(id_)) for id_ in batch]
            data = self.get(resource, params=params)
            results.extend(data.get(resource, []))
        return results
