from datetime import UTC, datetime

from steam_tracker import steam_api, steam_http

# ── resolve_friends ───────────────────────────────────────────────────────────


def test_resolve_friends_with_numeric_ids():
    result = steam_api.resolve_friends(["76561198001234567", "76561198009876543"])
    assert result == ["76561198001234567", "76561198009876543"]


def test_resolve_friends_empty():
    assert steam_api.resolve_friends([]) == []


def test_resolve_friends_calls_vanity(monkeypatch):
    monkeypatch.setattr(steam_api, "resolve_vanity_url", lambda _: "76561198000000001")
    assert steam_api.resolve_friends(["somevanity"]) == ["76561198000000001"]


def test_resolve_friends_skips_unresolvable_vanity(monkeypatch):
    monkeypatch.setattr(steam_api, "resolve_vanity_url", lambda _: None)
    assert steam_api.resolve_friends(["ghostuser"]) == []


# ── env var parsing ───────────────────────────────────────────────────────────


def test_friends_override_env_parsing():
    raw = " name1 , name2 ,, name3 "
    result = [friend.strip() for friend in raw.split(",") if friend.strip()]
    assert result == ["name1", "name2", "name3"]


# ── get_friend_ids ────────────────────────────────────────────────────────────


def test_get_friend_ids_returns_empty_on_api_failure(monkeypatch, capsys):
    monkeypatch.setattr(steam_api, "get", lambda *_: None)
    monkeypatch.setattr(steam_api, "FRIENDS_OVERRIDE", [])
    result = steam_api.get_friend_ids("76561198000000001")
    assert result == []
    assert "Friends list unavailable" in capsys.readouterr().out


# ── get_ytd_achievement_count sentinels ───────────────────────────────────────


def test_get_ytd_achievement_count_returns_blocked_on_403(monkeypatch):
    def fake_get(*_):
        steam_http._tls.last_status = 403
        return None

    monkeypatch.setattr(steam_api, "get", fake_get)
    assert (
        steam_api.get_ytd_achievement_count("steamid", 12345, 2026)
        == steam_api._BLOCKED
    )


def test_get_ytd_achievement_count_returns_server_error_on_500(monkeypatch):
    def fake_get(*_):
        steam_http._tls.last_status = 500
        return None

    monkeypatch.setattr(steam_api, "get", fake_get)
    assert (
        steam_api.get_ytd_achievement_count("steamid", 12345, 2026)
        == steam_api._SERVER_ERROR
    )


def test_get_ytd_achievement_count_returns_zero_on_network_failure(monkeypatch):
    monkeypatch.setattr(steam_api, "get", lambda *_: None)
    assert steam_api.get_ytd_achievement_count("steamid", 12345, 2026) == 0


def test_get_ytd_achievement_count_counts_only_target_year(monkeypatch):
    ts_in = int(datetime(2026, 3, 15, tzinfo=UTC).timestamp())
    ts_out = int(datetime(2025, 6, 1, tzinfo=UTC).timestamp())
    monkeypatch.setattr(
        steam_api,
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
    assert steam_api.get_ytd_achievement_count("steamid", 12345, 2026) == 2


def test_get_ytd_achievement_count_zero_when_no_achievements_in_year(monkeypatch):
    ts_old = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
    monkeypatch.setattr(
        steam_api,
        "get",
        lambda *_: {
            "playerstats": {"achievements": [{"achieved": 1, "unlocktime": ts_old}]}
        },
    )
    assert steam_api.get_ytd_achievement_count("steamid", 12345, 2026) == 0
