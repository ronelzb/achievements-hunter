from unittest.mock import MagicMock

import pytest

from steam_tracker import steam_http


@pytest.fixture
def mock_http(monkeypatch):
    """Offline HTTP layer: patches requests.get + time.sleep, returns the mock.

    Tests configure behaviour via mock_http.return_value or mock_http.side_effect.
    """
    mock_request = MagicMock()
    monkeypatch.setattr(steam_http.requests, "get", mock_request)
    monkeypatch.setattr(steam_http.time, "sleep", MagicMock())
    return mock_request
