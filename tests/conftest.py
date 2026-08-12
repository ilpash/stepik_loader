import time
from unittest.mock import MagicMock

import pytest

import resource_downloader


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", mock_sleep)
    return mock_sleep


@pytest.fixture
def mock_download_resource(monkeypatch):
    mock_download = MagicMock(return_value="local_resource")
    monkeypatch.setattr(resource_downloader, "download_resource", mock_download)
    return mock_download


class MockStepikClient:
    """
    Returns canned `data` per resource instead of hitting the network, and
    records every call in `get_by_ids_calls` as (resource, ids).
    """

    access_token = "mock-token"

    def __init__(self, data):
        self._data = data
        self.get_by_ids_calls = []

    def get_by_ids(self, resource, ids, batch_size=30):
        self.get_by_ids_calls.append((resource, list(ids)))
        return self._data[resource]
