from unittest.mock import MagicMock

import pytest
import steam_ytd_achievements as sya


@pytest.fixture
def mock_http(monkeypatch):
    """Offline HTTP layer: patches requests.get + time.sleep, returns the mock.

    Tests configure behaviour via mock_http.return_value or mock_http.side_effect.
    """
    mock_req = MagicMock()
    monkeypatch.setattr(sya.requests, "get", mock_req)
    monkeypatch.setattr(sya.time, "sleep", MagicMock())
    return mock_req


@pytest.fixture
def player_setup(monkeypatch):
    """Factory that wires up a player's game list and per-appid achievement counts.

    Usage:
        player_setup(games)                  # only patches get_owned_games
        player_setup(games, {1: 5, 2: 0})   # dict keyed by appid
        player_setup(games, 3)               # same count for every game
    """

    def _setup(games, counts=None):
        monkeypatch.setattr(sya, "get_owned_games", lambda _: games)
        if counts is None:
            return
        if isinstance(counts, dict):
            monkeypatch.setattr(
                sya, "get_ytd_achievement_count", lambda *args: counts[args[1]]
            )
        else:
            monkeypatch.setattr(sya, "get_ytd_achievement_count", lambda *_: counts)

    return _setup
