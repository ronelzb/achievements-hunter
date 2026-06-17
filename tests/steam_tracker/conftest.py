from unittest.mock import MagicMock

import pytest

from steam_tracker import steam_http


class MockResponse:
    """Minimal stand-in for a steamcommunity.com HTTP response."""

    def __init__(
        self,
        url: str = "https://steamcommunity.com/profiles/76561198000000000/",
        json_data: dict | None = None,
    ) -> None:
        self.url = url
        self._json_data = json_data or {}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._json_data


@pytest.fixture
def mock_response():
    """Returns the MockResponse class so tests can construct community response stubs."""
    return MockResponse


@pytest.fixture
def mock_http(monkeypatch):
    """Offline HTTP layer: patches requests.get + time.sleep, returns the mock.

    Tests configure behaviour via mock_http.return_value or mock_http.side_effect.
    """
    mock_request = MagicMock()
    monkeypatch.setattr(steam_http.requests, "get", mock_request)
    monkeypatch.setattr(steam_http.time, "sleep", MagicMock())
    return mock_request
