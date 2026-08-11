import time
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """
    Skip real retry/backoff delays in stepik_client and resource_downloader
    """
    mock_sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", mock_sleep)
    return mock_sleep


class MockStepikClient:
    """
    A StepikClient double that returns canned `data` per resource instead
    of hitting the network. Only implements what callers actually use:
    get_by_ids and access_token.

    Every call is recorded in `get_by_ids_calls` as (resource, ids), so tests
    can check which ids a caller asked for.
    """

    access_token = "mock-token"

    def __init__(self, data):
        self._data = data
        self.get_by_ids_calls = []

    def get_by_ids(self, resource, ids, batch_size=30):
        self.get_by_ids_calls.append((resource, list(ids)))
        return self._data[resource]
