import sys
from unittest.mock import MagicMock

import pytest

from steam_tracker import steam_game_achievements_cli, steam_http

_MY_ID = "76561198000000001"
_APP_ID = 220
_GAME_NAME = "Half-Life 2"

# Schema has not-won (index 0) then won (index 1) so sort order tests are meaningful:
# won-first changes the order, steam order preserves it.
_SCHEMA = [
    {
        "name": "ACH_LOSE",
        "displayName": "First Loss",
        "description": "Lose a game",
        "hidden": 0,
    },
    {
        "name": "ACH_WIN",
        "displayName": "First Win",
        "description": "Win a game",
        "hidden": 0,
    },
]

_PLAYER = [
    {"apiname": "ACH_LOSE", "achieved": 0, "unlocktime": 0},
    {"apiname": "ACH_WIN", "achieved": 1, "unlocktime": 1700000000},
]

_DEFAULT = object()  # sentinel: distinguishes "omitted" from explicit None


def _run(
    monkeypatch,
    argv=None,
    *,
    api_key="REAL_KEY",
    my_id: str | None = _MY_ID,
    search_results=None,
    schema=None,
    player=_DEFAULT,
    local_descs=None,
    user_input="",
):
    if search_results is None:
        search_results = [{"id": _APP_ID, "name": _GAME_NAME}]
    if schema is None:
        schema = (_GAME_NAME, _SCHEMA)
    if player is _DEFAULT:
        player = _PLAYER

    monkeypatch.setattr(steam_game_achievements_cli, "API_KEY", api_key)
    monkeypatch.setattr(steam_game_achievements_cli, "get_my_id", lambda *_: my_id)
    monkeypatch.setattr(
        steam_game_achievements_cli, "search_apps", lambda _: search_results
    )
    monkeypatch.setattr(
        steam_game_achievements_cli, "get_game_schema", lambda _: schema
    )
    monkeypatch.setattr(
        steam_game_achievements_cli,
        "get_all_player_achievements",
        lambda *_: player,
    )
    _local = local_descs if local_descs is not None else {}
    monkeypatch.setattr(
        steam_game_achievements_cli,
        "get_local_achievement_descs",
        lambda *_: _local,
    )
    monkeypatch.setattr(steam_http, "DEBUG", False)
    monkeypatch.setattr("builtins.input", lambda _: user_input)
    monkeypatch.setattr(sys, "argv", ["steam-game"] + (argv or [_GAME_NAME]))
    steam_game_achievements_cli.main()


# ── credential guard ──────────────────────────────────────────────────────────


def test_missing_api_key_prints_error(monkeypatch, capsys):
    _run(monkeypatch, api_key="YOUR_API_KEY_HERE")
    assert "STEAM_API_KEY" in capsys.readouterr().out


def test_missing_steam_id_prints_error(monkeypatch, capsys):
    _run(monkeypatch, my_id=None)
    assert "STEAM_ID" in capsys.readouterr().out


# ── no query / no app-id ──────────────────────────────────────────────────────


def test_no_query_and_no_app_id_exits(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["steam-game"])
    with pytest.raises(SystemExit):
        steam_game_achievements_cli.main()


# ── search flow ───────────────────────────────────────────────────────────────


def test_single_result_auto_picked(monkeypatch, capsys):
    _run(monkeypatch, search_results=[{"id": _APP_ID, "name": _GAME_NAME}])
    assert _GAME_NAME in capsys.readouterr().out


def test_no_search_results_prints_error(monkeypatch, capsys):
    _run(monkeypatch, search_results=[])
    assert "No games found" in capsys.readouterr().out


def test_multiple_results_shows_numbered_list(monkeypatch, capsys):
    results = [
        {"id": 220, "name": "Half-Life 2"},
        {"id": 221, "name": "Half-Life 2: Deathmatch"},
    ]
    _run(monkeypatch, search_results=results, user_input="")
    out = capsys.readouterr().out
    assert "Half-Life 2" in out
    assert "Half-Life 2: Deathmatch" in out


def test_multiple_results_user_picks_by_number(monkeypatch, capsys):
    results = [
        {"id": 220, "name": "Half-Life 2"},
        {"id": 221, "name": "Half-Life 2: Deathmatch"},
    ]
    _run(monkeypatch, search_results=results, user_input="2")
    # schema_name (_GAME_NAME) is used as app_name because search result name is ignored
    # after _pick_app returns id=221; schema returns ("Half-Life 2", ...) regardless
    out = capsys.readouterr().out
    assert "221" in out


def test_multiple_results_empty_input_cancels(monkeypatch, capsys):
    results = [
        {"id": 220, "name": "Half-Life 2"},
        {"id": 221, "name": "Half-Life 2: Deathmatch"},
    ]
    _run(monkeypatch, search_results=results, user_input="")
    # cancelled — no achievement table
    assert "Achievements:" not in capsys.readouterr().out


# ── --app-id ──────────────────────────────────────────────────────────────────


def test_app_id_skips_search(monkeypatch, capsys):
    mock_search = MagicMock()
    monkeypatch.setattr(steam_game_achievements_cli, "API_KEY", "REAL_KEY")
    monkeypatch.setattr(steam_game_achievements_cli, "get_my_id", lambda *_: _MY_ID)
    monkeypatch.setattr(steam_game_achievements_cli, "search_apps", mock_search)
    monkeypatch.setattr(
        steam_game_achievements_cli,
        "get_game_schema",
        lambda _: (_GAME_NAME, _SCHEMA),
    )
    monkeypatch.setattr(
        steam_game_achievements_cli,
        "get_all_player_achievements",
        lambda *_: _PLAYER,
    )
    monkeypatch.setattr(steam_http, "DEBUG", False)
    monkeypatch.setattr(sys, "argv", ["steam-game", "--app-id", str(_APP_ID)])
    steam_game_achievements_cli.main()
    mock_search.assert_not_called()


def test_app_id_uses_schema_name_as_game_name(monkeypatch, capsys):
    _run(monkeypatch, argv=["--app-id", str(_APP_ID)])
    assert _GAME_NAME in capsys.readouterr().out


# ── schema / player errors ────────────────────────────────────────────────────


def test_empty_schema_prints_error(monkeypatch, capsys):
    _run(monkeypatch, schema=("", []))
    assert "No achievements found" in capsys.readouterr().out


def test_blocked_achievements_prints_error(monkeypatch, capsys):
    _run(monkeypatch, player=None)
    assert "Could not fetch" in capsys.readouterr().out


# ── table output ──────────────────────────────────────────────────────────────


def test_shows_game_name_and_app_id(monkeypatch, capsys):
    _run(monkeypatch)
    out = capsys.readouterr().out
    assert _GAME_NAME in out
    assert str(_APP_ID) in out


def test_shows_achievement_percentage(monkeypatch, capsys):
    _run(monkeypatch)
    out = capsys.readouterr().out
    assert "1 / 2" in out
    assert "50.0%" in out


def test_won_achievement_appears_in_output(monkeypatch, capsys):
    _run(monkeypatch)
    assert "First Win" in capsys.readouterr().out


def test_not_won_achievement_appears_in_output(monkeypatch, capsys):
    _run(monkeypatch)
    assert "First Loss" in capsys.readouterr().out


def test_unlock_date_shown_for_won_achievement(monkeypatch, capsys):
    _run(monkeypatch)
    assert "2023-11-14" in capsys.readouterr().out  # unlocktime 1700000000


def test_dash_shown_for_not_won_achievement(monkeypatch, capsys):
    _run(monkeypatch)
    assert "—" in capsys.readouterr().out


def test_hidden_achievement_shows_placeholder_description(monkeypatch, capsys):
    schema = [
        {"name": "ACH_SECRET", "displayName": "Secret", "description": "", "hidden": 1}
    ]
    player = [{"apiname": "ACH_SECRET", "achieved": 0, "unlocktime": 0}]
    _run(monkeypatch, schema=(_GAME_NAME, schema), player=player)
    assert "(Hidden)" in capsys.readouterr().out


def test_won_hidden_achievement_shows_player_description_not_placeholder(
    monkeypatch, capsys
):
    schema = [
        {"name": "ACH_SECRET", "displayName": "Secret", "description": "", "hidden": 1}
    ]
    player = [
        {
            "apiname": "ACH_SECRET",
            "achieved": 1,
            "unlocktime": 1700000000,
            "description": "You found it!",
        }
    ]
    _run(monkeypatch, schema=(_GAME_NAME, schema), player=player)
    out = capsys.readouterr().out
    assert "You found it!" in out
    assert "(Hidden)" not in out


def test_reveal_hidden_shows_schema_description_for_not_won(monkeypatch, capsys):
    schema = [
        {
            "name": "ACH_SECRET",
            "displayName": "Secret",
            "description": "Spoiler text",
            "hidden": 1,
        }
    ]
    player = [{"apiname": "ACH_SECRET", "achieved": 0, "unlocktime": 0}]
    _run(
        monkeypatch,
        argv=[_GAME_NAME, "--reveal-hidden"],
        schema=(_GAME_NAME, schema),
        player=player,
    )
    out = capsys.readouterr().out
    assert "Spoiler text" in out
    assert "(Hidden)" not in out


def test_reveal_hidden_clears_placeholder_when_no_description(monkeypatch, capsys):
    schema = [
        {"name": "ACH_SECRET", "displayName": "Secret", "description": "", "hidden": 1}
    ]
    player = [{"apiname": "ACH_SECRET", "achieved": 0, "unlocktime": 0}]
    _run(
        monkeypatch,
        argv=[_GAME_NAME, "--reveal-hidden"],
        schema=(_GAME_NAME, schema),
        player=player,
    )
    assert "(Hidden)" not in capsys.readouterr().out


# ── [SteamCache] indicator ────────────────────────────────────────────────────


def test_local_desc_shown_with_cache_indicator_for_not_won(monkeypatch, capsys):
    schema = [
        {"name": "ACH_SECRET", "displayName": "Secret", "description": "", "hidden": 0}
    ]
    player = [{"apiname": "ACH_SECRET", "achieved": 0, "unlocktime": 0}]
    _run(
        monkeypatch,
        schema=(_GAME_NAME, schema),
        player=player,
        local_descs={"ACH_SECRET": "From local cache."},
    )
    out = capsys.readouterr().out
    assert "From local cache." in out
    assert "[SteamCache]" in out


def test_local_desc_shown_with_cache_indicator_when_won(monkeypatch, capsys):
    schema = [
        {"name": "ACH_SECRET", "displayName": "Secret", "description": "", "hidden": 0}
    ]
    player = [
        {
            "apiname": "ACH_SECRET",
            "achieved": 1,
            "unlocktime": 1700000000,
            "description": "",
        }
    ]
    _run(
        monkeypatch,
        schema=(_GAME_NAME, schema),
        player=player,
        local_descs={"ACH_SECRET": "From local cache."},
    )
    out = capsys.readouterr().out
    assert "From local cache." in out
    assert "[SteamCache]" in out


def test_local_desc_not_used_when_schema_desc_present(monkeypatch, capsys):
    schema = [
        {
            "name": "ACH_WIN",
            "displayName": "First Win",
            "description": "Win a game",
            "hidden": 0,
        }
    ]
    player = [{"apiname": "ACH_WIN", "achieved": 0, "unlocktime": 0}]
    _run(
        monkeypatch,
        schema=(_GAME_NAME, schema),
        player=player,
        local_descs={"ACH_WIN": "Local override."},
    )
    out = capsys.readouterr().out
    assert "Win a game" in out
    assert "[SteamCache]" not in out


# ── --filter ──────────────────────────────────────────────────────────────────


def test_filter_won_shows_only_won(monkeypatch, capsys):
    _run(monkeypatch, argv=[_GAME_NAME, "--filter", "won"])
    out = capsys.readouterr().out
    assert "First Win" in out
    assert "First Loss" not in out


def test_filter_not_won_shows_only_not_won(monkeypatch, capsys):
    _run(monkeypatch, argv=[_GAME_NAME, "--filter", "not-won"])
    out = capsys.readouterr().out
    assert "First Loss" in out
    assert "First Win" not in out


def test_filter_all_shows_both(monkeypatch, capsys):
    _run(monkeypatch, argv=[_GAME_NAME, "--filter", "all"])
    out = capsys.readouterr().out
    assert "First Win" in out
    assert "First Loss" in out


def test_filter_won_empty_result_prints_message(monkeypatch, capsys):
    player_none_won = [
        {"apiname": "ACH_LOSE", "achieved": 0, "unlocktime": 0},
        {"apiname": "ACH_WIN", "achieved": 0, "unlocktime": 0},
    ]
    _run(monkeypatch, argv=[_GAME_NAME, "--filter", "won"], player=player_none_won)
    assert "no achievements match" in capsys.readouterr().out


# ── --sort ────────────────────────────────────────────────────────────────────


def test_default_sort_puts_won_before_not_won(monkeypatch, capsys):
    # Schema: not-won (index 0), won (index 1) — won-first changes the order
    _run(monkeypatch)
    out = capsys.readouterr().out
    assert out.index("First Win") < out.index("First Loss")


def test_sort_steam_preserves_schema_order(monkeypatch, capsys):
    # Schema: not-won (index 0), won (index 1) — steam order keeps that
    _run(monkeypatch, argv=[_GAME_NAME, "--sort", "steam"])
    out = capsys.readouterr().out
    assert out.index("First Loss") < out.index("First Win")


def test_sort_steam_shows_schema_index_in_number_column(monkeypatch, capsys):
    # Schema: [Loss(idx=1), Win(idx=2)], filter to won — only Win remains
    # With steam sort, # = schema index (2), not row number (1)
    _run(monkeypatch, argv=[_GAME_NAME, "--sort", "steam", "--filter", "won"])
    out = capsys.readouterr().out
    win_line = next(line for line in out.splitlines() if "First Win" in line)
    assert win_line.strip().startswith("2")


def test_default_sort_shows_sequential_row_number(monkeypatch, capsys):
    # Schema: [Loss(idx=1), Win(idx=2)], filter to won — only Win remains
    # With won-first sort, # = row number (1), not schema index (2)
    _run(monkeypatch, argv=[_GAME_NAME, "--filter", "won"])
    out = capsys.readouterr().out
    win_line = next(line for line in out.splitlines() if "First Win" in line)
    assert win_line.strip().startswith("1")


# ── --debug ───────────────────────────────────────────────────────────────────


def test_debug_flag_sets_steam_http_debug(monkeypatch):
    _run(monkeypatch, argv=[_GAME_NAME, "--debug"])
    assert steam_http.DEBUG is True


def test_no_debug_flag_leaves_steam_http_debug_false(monkeypatch):
    _run(monkeypatch)
    assert steam_http.DEBUG is False
