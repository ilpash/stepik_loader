import time
from unittest.mock import MagicMock

import pytest

import export_course
import stepik_client


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", mock_sleep)
    return mock_sleep


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    mock_load_dotenv = MagicMock()
    monkeypatch.setattr(export_course, "load_dotenv", mock_load_dotenv)
    return mock_load_dotenv


@pytest.fixture(autouse=True)
def temporary_token_cache(tmp_path, monkeypatch):
    token_cache = tmp_path / "stepik_token.json"
    monkeypatch.setattr(stepik_client, "DEFAULT_TOKEN_CACHE", token_cache)
    return token_cache


class MockStepikClient:
    """
    Returns canned `data` per resource instead of hitting the network, and
    records every call in `get_by_ids_calls` as (resource, ids).
    """

    access_token = "mock-token"

    def __init__(self, data):
        self._data = data
        self.get_by_ids_calls = []

    def get_by_ids(self, resource, ids):
        self.get_by_ids_calls.append((resource, list(ids)))
        return self._data[resource]
