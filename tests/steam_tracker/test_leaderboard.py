import pytest

from steam_tracker import leaderboard, steam_api


@pytest.fixture
def player_setup(monkeypatch):
    """Factory that wires up a player's game list and per-appid achievement counts.

    Usage:
        player_setup(games)                  # only patches get_owned_games
        player_setup(games, {1: 5, 2: 0})   # dict keyed by appid
        player_setup(games, 3)               # same count for every game
    """

    def _setup(games, counts=None):
        monkeypatch.setattr(leaderboard, "get_owned_games", lambda _: games)
        if counts is None:
            return
        if isinstance(counts, dict):
            monkeypatch.setattr(
                leaderboard,
                "get_ytd_achievement_count",
                lambda *args: counts[args[1]],
            )
        else:
            monkeypatch.setattr(
                leaderboard, "get_ytd_achievement_count", lambda *_: counts
            )

    return _setup


# ── has_community_visible_stats pre-filter ────────────────────────────────────
# Steam returns 500 (not 400) for games with no achievement schema. We avoid
# the call entirely using the has_community_visible_stats flag from GetOwnedGames.


def test_count_skips_games_without_achievement_schema(player_setup, monkeypatch):
    games = [
        {"appid": 1, "playtime_forever": 100, "has_community_visible_stats": True},
        {"appid": 2, "playtime_forever": 50},  # no schema → must be skipped
        {"appid": 3, "playtime_forever": 200, "has_community_visible_stats": True},
    ]
    called = []
    player_setup(games)
    monkeypatch.setattr(
        leaderboard,
        "get_ytd_achievement_count",
        lambda *args: called.append(args[1]) or 0,
    )
    leaderboard.count_ytd_achievements_for_player("steamid", 2026)
    assert set(called) == {1, 3}
    assert 2 not in called


def test_count_skips_unplayed_games(player_setup, monkeypatch):
    games = [
        {"appid": 1, "playtime_forever": 0, "has_community_visible_stats": True},
        {"appid": 2, "playtime_forever": 100, "has_community_visible_stats": True},
    ]
    called = []
    player_setup(games)
    monkeypatch.setattr(
        leaderboard,
        "get_ytd_achievement_count",
        lambda *args: called.append(args[1]) or 0,
    )
    leaderboard.count_ytd_achievements_for_player("steamid", 2026)
    assert called == [2]


def test_count_verbose_shows_schema_skip_count(player_setup, capsys):
    games = [
        {"appid": 1, "playtime_forever": 100, "has_community_visible_stats": True},
        {"appid": 2, "playtime_forever": 50},  # no schema
        {"appid": 3, "playtime_forever": 200},  # no schema
    ]
    player_setup(games, counts=0)
    leaderboard.count_ytd_achievements_for_player("steamid", 2026, verbose=True)
    assert "2 skipped (no achievement schema)" in capsys.readouterr().out


def test_count_returns_zero_when_no_games(player_setup):
    player_setup([])
    assert leaderboard.count_ytd_achievements_for_player("steamid", 2026) == 0


# ── count aggregation and per-game failure reporting ─────────────────────────


def test_count_total_excludes_blocked_and_server_error(player_setup):
    per_app = {1: 10, 2: steam_api._BLOCKED, 3: steam_api._SERVER_ERROR, 4: 5}
    games = [
        {"appid": app_id, "playtime_forever": 10, "has_community_visible_stats": True}
        for app_id in per_app
    ]
    player_setup(games, per_app)
    assert (
        leaderboard.count_ytd_achievements_for_player("steamid", 2026) == 15
    )  # 10 + 5


def test_count_verbose_names_blocked_and_failed_games(player_setup, capsys):
    games = [
        {
            "appid": 1,
            "name": "Good Game",
            "playtime_forever": 10,
            "has_community_visible_stats": True,
        },
        {
            "appid": 2,
            "name": "Private Game",
            "playtime_forever": 10,
            "has_community_visible_stats": True,
        },
        {
            "appid": 3,
            "name": "Broken Server",
            "playtime_forever": 10,
            "has_community_visible_stats": True,
        },
    ]
    player_setup(games, {1: 7, 2: steam_api._BLOCKED, 3: steam_api._SERVER_ERROR})
    leaderboard.count_ytd_achievements_for_player("steamid", 2026, verbose=True)
    out = capsys.readouterr().out
    assert "→ 7 achievements" in out
    assert "blocked" in out and "Private Game" in out
    assert "server error" in out and "Broken Server" in out


def test_count_verbose_no_warning_when_all_succeed(player_setup, capsys):
    games = [
        {
            "appid": 1,
            "name": "Clean Game",
            "playtime_forever": 10,
            "has_community_visible_stats": True,
        },
    ]
    player_setup(games, counts=3)
    leaderboard.count_ytd_achievements_for_player("steamid", 2026, verbose=True)
    out = capsys.readouterr().out
    assert "⚠" not in out
    assert "→ 3 achievements" in out
