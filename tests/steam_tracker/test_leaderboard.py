from unittest.mock import MagicMock

import pytest

from steam_tracker import leaderboard, steam_api

_MY_ID = "00000"
_FRIEND_A = "11111"
_FRIEND_B = "22222"
_NAMES = {_MY_ID: "Me", _FRIEND_A: "Zephyr", _FRIEND_B: "AlphaGamer"}


def _setup_build(monkeypatch, friend_ids=None, names=None):
    """Wire up build_leaderboard dependencies."""
    monkeypatch.setattr(
        leaderboard, "get_friend_ids", lambda _: friend_ids or [_FRIEND_A, _FRIEND_B]
    )
    monkeypatch.setattr(
        leaderboard, "get_player_summaries_bulk", lambda _: names or _NAMES
    )
    monkeypatch.setattr(
        leaderboard, "count_ytd_achievements_for_player", MagicMock(return_value=0)
    )


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


# ── build_leaderboard filter ──────────────────────────────────────────────────


def test_build_leaderboard_filter_excludes_non_matching_friends(monkeypatch):
    _setup_build(monkeypatch)
    mock = MagicMock(return_value=0)
    monkeypatch.setattr(leaderboard, "count_ytd_achievements_for_player", mock)
    leaderboard.build_leaderboard(2026, _MY_ID, filter_names=["zephyr"])
    called_ids = {call.args[0] for call in mock.call_args_list}
    assert _FRIEND_A in called_ids
    assert _FRIEND_B not in called_ids


def test_build_leaderboard_filter_always_includes_me(monkeypatch):
    _setup_build(monkeypatch)
    mock = MagicMock(return_value=0)
    monkeypatch.setattr(leaderboard, "count_ytd_achievements_for_player", mock)
    leaderboard.build_leaderboard(2026, _MY_ID, filter_names=["zzznomatch"])
    called_ids = {call.args[0] for call in mock.call_args_list}
    assert _MY_ID in called_ids


def test_build_leaderboard_filter_is_case_insensitive(monkeypatch):
    _setup_build(monkeypatch)
    mock = MagicMock(return_value=0)
    monkeypatch.setattr(leaderboard, "count_ytd_achievements_for_player", mock)
    leaderboard.build_leaderboard(2026, _MY_ID, filter_names=["ALPHA"])
    called_ids = {call.args[0] for call in mock.call_args_list}
    assert _FRIEND_B in called_ids
    assert _FRIEND_A not in called_ids


def test_build_leaderboard_filter_supports_partial_match(monkeypatch):
    _setup_build(monkeypatch)
    mock = MagicMock(return_value=0)
    monkeypatch.setattr(leaderboard, "count_ytd_achievements_for_player", mock)
    leaderboard.build_leaderboard(2026, _MY_ID, filter_names=["eph"])
    called_ids = {call.args[0] for call in mock.call_args_list}
    assert _FRIEND_A in called_ids
    assert _FRIEND_B not in called_ids


def test_build_leaderboard_filter_debug_warns_unmatched_term(monkeypatch, capsys):
    _setup_build(monkeypatch)
    leaderboard.build_leaderboard(
        2026, _MY_ID, filter_names=["zephyr", "zzznomatch"], debug=True
    )
    out = capsys.readouterr().out
    assert "'zzznomatch'" in out
    assert "no friends matched" in out
    assert "friends searched" in out


def test_build_leaderboard_filter_debug_silent_when_all_match(monkeypatch, capsys):
    _setup_build(monkeypatch)
    leaderboard.build_leaderboard(2026, _MY_ID, filter_names=["zephyr"], debug=True)
    out = capsys.readouterr().out
    assert "no friends matched" not in out
    assert "friends searched" not in out


def test_build_leaderboard_no_filter_includes_all_friends(monkeypatch):
    _setup_build(monkeypatch)
    mock = MagicMock(return_value=0)
    monkeypatch.setattr(leaderboard, "count_ytd_achievements_for_player", mock)
    leaderboard.build_leaderboard(2026, _MY_ID)
    called_ids = {call.args[0] for call in mock.call_args_list}
    assert _MY_ID in called_ids
    assert _FRIEND_A in called_ids
    assert _FRIEND_B in called_ids
