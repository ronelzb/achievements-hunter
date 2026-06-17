from datetime import UTC, datetime
from unittest.mock import MagicMock

import steam_ytd_achievements as sya

# ── resolve_friends ───────────────────────────────────────────────────────────


def test_resolve_friends_with_numeric_ids():
    result = sya.resolve_friends(["76561198001234567", "76561198009876543"])
    assert result == ["76561198001234567", "76561198009876543"]


def test_resolve_friends_empty():
    assert sya.resolve_friends([]) == []


def test_resolve_friends_calls_vanity(monkeypatch):
    monkeypatch.setattr(sya, "resolve_vanity_url", lambda _: "76561198000000001")
    assert sya.resolve_friends(["somevanity"]) == ["76561198000000001"]


def test_resolve_friends_skips_unresolvable_vanity(monkeypatch):
    monkeypatch.setattr(sya, "resolve_vanity_url", lambda _: None)
    assert sya.resolve_friends(["ghostuser"]) == []


# ── env var parsing ───────────────────────────────────────────────────────────


def test_friends_override_env_parsing():
    raw = " name1 , name2 ,, name3 "
    result = [f.strip() for f in raw.split(",") if f.strip()]
    assert result == ["name1", "name2", "name3"]


# ── get_friend_ids ────────────────────────────────────────────────────────────


def test_get_friend_ids_returns_empty_on_api_failure(monkeypatch, capsys):
    monkeypatch.setattr(sya, "get", lambda *_: None)
    monkeypatch.setattr(sya, "FRIENDS_OVERRIDE", [])
    result = sya.get_friend_ids("76561198000000001")
    assert result == []
    assert "Friends list unavailable" in capsys.readouterr().out


# ── HTTP retry / error logic ──────────────────────────────────────────────────


def test_get_retries_on_500_and_succeeds(mock_http):
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"result": "ok"}
    mock_http.side_effect = [MagicMock(status_code=500, text="error"), ok]
    assert sya.get("endpoint", {}) == {"result": "ok"}


def test_get_exhausts_retries_on_persistent_500(mock_http):
    mock_http.return_value = MagicMock(status_code=500, text="err")
    assert sya.get("endpoint", {}) is None


def test_get_does_not_retry_on_4xx(mock_http):
    mock_http.return_value = MagicMock(status_code=403, text="Forbidden")
    assert sya.get("endpoint", {}) is None
    assert mock_http.call_count == 1  # no retries for deterministic client errors


def test_get_sets_last_status_on_error(mock_http):
    mock_http.return_value = MagicMock(status_code=403, text="err")
    sya._tls.last_status = None
    sya.get("endpoint", {})
    assert sya._tls.last_status == 403


# ── get_ytd_achievement_count sentinels ───────────────────────────────────────


def test_get_ytd_achievement_count_returns_blocked_on_403(monkeypatch):
    def fake_get(*_):
        sya._tls.last_status = 403
        return None

    monkeypatch.setattr(sya, "get", fake_get)
    assert sya.get_ytd_achievement_count("steamid", 12345, 2026) == sya._BLOCKED


def test_get_ytd_achievement_count_returns_server_error_on_500(monkeypatch):
    def fake_get(*_):
        sya._tls.last_status = 500
        return None

    monkeypatch.setattr(sya, "get", fake_get)
    assert sya.get_ytd_achievement_count("steamid", 12345, 2026) == sya._SERVER_ERROR


def test_get_ytd_achievement_count_returns_zero_on_network_failure(monkeypatch):
    # No HTTP response (e.g. connection refused) — last_status stays None
    monkeypatch.setattr(sya, "get", lambda *_: None)
    assert sya.get_ytd_achievement_count("steamid", 12345, 2026) == 0


def test_get_ytd_achievement_count_counts_only_target_year(monkeypatch):
    ts_in = int(datetime(2026, 3, 15, tzinfo=UTC).timestamp())
    ts_out = int(datetime(2025, 6, 1, tzinfo=UTC).timestamp())
    monkeypatch.setattr(
        sya,
        "get",
        lambda *_: {
            "playerstats": {
                "achievements": [
                    {"achieved": 1, "unlocktime": ts_in},  # counts
                    {"achieved": 1, "unlocktime": ts_out},  # wrong year
                    {"achieved": 0, "unlocktime": ts_in},  # not achieved
                    {"achieved": 1, "unlocktime": ts_in},  # counts
                ]
            }
        },
    )
    assert sya.get_ytd_achievement_count("steamid", 12345, 2026) == 2


def test_get_ytd_achievement_count_zero_when_no_achievements_in_year(monkeypatch):
    ts_old = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
    monkeypatch.setattr(
        sya,
        "get",
        lambda *_: {
            "playerstats": {"achievements": [{"achieved": 1, "unlocktime": ts_old}]}
        },
    )
    assert sya.get_ytd_achievement_count("steamid", 12345, 2026) == 0


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
        sya, "get_ytd_achievement_count", lambda *args: called.append(args[1]) or 0
    )
    sya.count_ytd_achievements_for_player("steamid", 2026)
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
        sya, "get_ytd_achievement_count", lambda *args: called.append(args[1]) or 0
    )
    sya.count_ytd_achievements_for_player("steamid", 2026)
    assert called == [2]


def test_count_verbose_shows_schema_skip_count(player_setup, capsys):
    games = [
        {"appid": 1, "playtime_forever": 100, "has_community_visible_stats": True},
        {"appid": 2, "playtime_forever": 50},  # no schema
        {"appid": 3, "playtime_forever": 200},  # no schema
    ]
    player_setup(games, counts=0)
    sya.count_ytd_achievements_for_player("steamid", 2026, verbose=True)
    assert "2 skipped (no achievement schema)" in capsys.readouterr().out


def test_count_returns_zero_when_no_games(player_setup):
    player_setup([])
    assert sya.count_ytd_achievements_for_player("steamid", 2026) == 0


# ── count aggregation and per-game failure reporting ─────────────────────────


def test_count_total_excludes_blocked_and_server_error(player_setup):
    per_app = {1: 10, 2: sya._BLOCKED, 3: sya._SERVER_ERROR, 4: 5}
    games = [
        {"appid": a, "playtime_forever": 10, "has_community_visible_stats": True}
        for a in per_app
    ]
    player_setup(games, per_app)
    assert sya.count_ytd_achievements_for_player("steamid", 2026) == 15  # 10 + 5


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
    player_setup(games, {1: 7, 2: sya._BLOCKED, 3: sya._SERVER_ERROR})
    sya.count_ytd_achievements_for_player("steamid", 2026, verbose=True)
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
    sya.count_ytd_achievements_for_player("steamid", 2026, verbose=True)
    out = capsys.readouterr().out
    assert "⚠" not in out
    assert "→ 3 achievements" in out


# ── print_leaderboard ─────────────────────────────────────────────────────────


def test_print_leaderboard_formats_output(capsys):
    results = [
        {"name": "Alice", "count": 50, "is_me": True, "steam_id": "1"},
        {"name": "Bob", "count": 30, "is_me": False, "steam_id": "2"},
    ]
    sya.print_leaderboard(results, 2026)
    out = capsys.readouterr().out
    assert "Alice" in out
    assert "50" in out
    assert "YOU" in out
    assert "🥇" in out


def test_print_leaderboard_shows_rank_when_not_first(capsys):
    results = [
        {"name": "Bob", "count": 80, "is_me": False, "steam_id": "2"},
        {"name": "Alice", "count": 50, "is_me": True, "steam_id": "1"},
    ]
    sya.print_leaderboard(results, 2026)
    out = capsys.readouterr().out
    assert "#2" in out
    assert "Bob leads by 30" in out


def test_print_leaderboard_celebrates_first_place(capsys):
    results = [
        {"name": "Alice", "count": 100, "is_me": True, "steam_id": "1"},
        {"name": "Bob", "count": 50, "is_me": False, "steam_id": "2"},
    ]
    sya.print_leaderboard(results, 2026)
    out = capsys.readouterr().out
    assert "🏆" in out
    assert "#1" in out
