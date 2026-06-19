import sys

from steam_tracker import steam_friends_cli, steam_http

_STEAM_ID = "76561198000000000"
_FRIEND_IDS = ["76561198000000001", "76561198000000002"]
_PLAYERS = [
    {
        "steamid": "76561198000000001",
        "personaname": "Zephyr",
        "realname": "John Doe",
        "communityvisibilitystate": 3,
    },
    {
        "steamid": "76561198000000002",
        "personaname": "AlphaGamer",
        "realname": "",
        "communityvisibilitystate": 1,
    },
]


def _run(
    monkeypatch,
    argv=None,
    *,
    api_key="REAL_KEY",
    my_id: str | None = _STEAM_ID,
    session_id: str | None = None,
    friend_ids=_FRIEND_IDS,
    players=_PLAYERS,
):
    monkeypatch.setattr(steam_friends_cli, "API_KEY", api_key)
    monkeypatch.setattr(steam_friends_cli, "get_my_id", lambda *_: my_id or session_id)
    monkeypatch.setattr(steam_friends_cli, "get_friend_ids", lambda _: friend_ids)
    monkeypatch.setattr(
        steam_friends_cli, "get_player_summaries_bulk_full", lambda _: list(players)
    )
    monkeypatch.setattr(steam_http, "DEBUG", False)
    monkeypatch.setattr(sys, "argv", ["steam-friends"] + (argv or []))
    steam_friends_cli.main()


# ── credential guard ──────────────────────────────────────────────────────────


def test_main_prints_error_when_api_key_is_placeholder(monkeypatch, capsys):
    _run(monkeypatch, api_key="YOUR_API_KEY_HERE")
    assert "STEAM_API_KEY" in capsys.readouterr().out


def test_main_prints_error_when_steam_id_not_set(monkeypatch, capsys):
    _run(monkeypatch, my_id=None, session_id=None)
    assert "STEAM_ID" in capsys.readouterr().out


# ── Steam ID resolution ───────────────────────────────────────────────────────


def test_main_uses_session_id_when_my_id_not_set(monkeypatch, capsys):
    _run(monkeypatch, my_id=None, session_id=_STEAM_ID)
    assert "No friends found" not in capsys.readouterr().out


# ── no friends ────────────────────────────────────────────────────────────────


def test_main_prints_message_when_no_friends(monkeypatch, capsys):
    _run(monkeypatch, friend_ids=[])
    assert "No friends found" in capsys.readouterr().out


# ── table output ──────────────────────────────────────────────────────────────


def test_main_prints_display_names(monkeypatch, capsys):
    _run(monkeypatch)
    out = capsys.readouterr().out
    assert "Zephyr" in out
    assert "AlphaGamer" in out


def test_main_prints_steam_ids(monkeypatch, capsys):
    _run(monkeypatch)
    out = capsys.readouterr().out
    assert "76561198000000001" in out
    assert "76561198000000002" in out


def test_main_prints_real_name_when_set(monkeypatch, capsys):
    _run(monkeypatch)
    assert "John Doe" in capsys.readouterr().out


def test_main_prints_dash_when_real_name_absent(monkeypatch, capsys):
    _run(monkeypatch, players=[_PLAYERS[1]])
    out = capsys.readouterr().out
    assert "—" in out


def test_main_shows_visibility_labels(monkeypatch, capsys):
    _run(monkeypatch)
    out = capsys.readouterr().out
    assert "Public" in out
    assert "Private" in out


def test_main_sorts_alphabetically(monkeypatch, capsys):
    _run(monkeypatch)
    out = capsys.readouterr().out
    assert out.index("AlphaGamer") < out.index("Zephyr")


# ── --filter ──────────────────────────────────────────────────────────────────


def test_filter_matches_case_insensitively(monkeypatch, capsys):
    _run(monkeypatch, argv=["--filter", "zephyr"])
    out = capsys.readouterr().out
    assert "Zephyr" in out
    assert "AlphaGamer" not in out


def test_filter_supports_partial_match(monkeypatch, capsys):
    _run(monkeypatch, argv=["--filter", "alpha"])
    out = capsys.readouterr().out
    assert "AlphaGamer" in out
    assert "Zephyr" not in out


def test_filter_multiple_terms(monkeypatch, capsys):
    _run(monkeypatch, argv=["--filter", "zephyr", "alpha"])
    out = capsys.readouterr().out
    assert "Zephyr" in out
    assert "AlphaGamer" in out


def test_filter_prints_message_when_no_match(monkeypatch, capsys):
    _run(monkeypatch, argv=["--filter", "zzznomatch"])
    assert "No friends match" in capsys.readouterr().out


def test_filter_debug_warns_unmatched_terms(monkeypatch, capsys):
    _run(monkeypatch, argv=["--filter", "zephyr", "zzznomatch", "--debug"])
    out = capsys.readouterr().out
    assert "'zzznomatch'" in out
    assert "no friends matched" in out
    assert "friends searched" in out


def test_filter_debug_silent_when_all_terms_match(monkeypatch, capsys):
    _run(monkeypatch, argv=["--filter", "zephyr", "--debug"])
    out = capsys.readouterr().out
    assert "no friends matched" not in out
    assert "friends searched" not in out


# ── --debug ───────────────────────────────────────────────────────────────────


def test_debug_flag_sets_steam_http_debug(monkeypatch):
    _run(monkeypatch, argv=["--debug"])
    assert steam_http.DEBUG is True


def test_no_debug_flag_leaves_steam_http_debug_false(monkeypatch):
    _run(monkeypatch)
    assert steam_http.DEBUG is False
