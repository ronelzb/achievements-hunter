import sys
from unittest.mock import MagicMock

from steam_tracker import leaderboard_cli

_MY_ID = "76561198000000001"

# ── print_leaderboard ─────────────────────────────────────────────────────────


def test_print_leaderboard_formats_output(capsys):
    results = [
        {"name": "Alice", "count": 50, "is_me": True, "steam_id": "1"},
        {"name": "Bob", "count": 30, "is_me": False, "steam_id": "2"},
    ]
    leaderboard_cli.print_leaderboard(results, 2026)
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
    leaderboard_cli.print_leaderboard(results, 2026)
    out = capsys.readouterr().out
    assert "#2" in out
    assert "Bob leads by 30" in out


def test_print_leaderboard_celebrates_first_place(capsys):
    results = [
        {"name": "Alice", "count": 100, "is_me": True, "steam_id": "1"},
        {"name": "Bob", "count": 50, "is_me": False, "steam_id": "2"},
    ]
    leaderboard_cli.print_leaderboard(results, 2026)
    out = capsys.readouterr().out
    assert "🏆" in out
    assert "#1" in out


# ── helpers ───────────────────────────────────────────────────────────────────


def _run(
    monkeypatch, argv, *, my_id: str | None = _MY_ID, session_id: str | None = None
):
    captured: dict = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return [{"name": "Me", "count": 0, "is_me": True, "steam_id": my_id or ""}]

    monkeypatch.setattr(leaderboard_cli, "API_KEY", "REAL_KEY")
    monkeypatch.setattr(leaderboard_cli, "get_my_id", lambda **_: my_id or session_id)
    monkeypatch.setattr(leaderboard_cli, "load_session", lambda: None)
    monkeypatch.setattr(leaderboard_cli, "build_leaderboard", fake_build)
    monkeypatch.setattr(leaderboard_cli, "print_leaderboard", MagicMock())
    monkeypatch.setattr(sys, "argv", argv)
    leaderboard_cli.main()
    return captured


# ── --filter forwarding ───────────────────────────────────────────────────────


def test_main_passes_filter_to_build_leaderboard(monkeypatch):
    captured = _run(monkeypatch, ["steam-leaderboard", "--filter", "zephyr", "alpha"])
    assert captured["filter_names"] == ["zephyr", "alpha"]


def test_main_passes_none_filter_when_not_provided(monkeypatch):
    captured = _run(monkeypatch, ["steam-leaderboard"])
    assert captured["filter_names"] is None


def test_main_passes_my_id_to_build_leaderboard(monkeypatch):
    captured = _run(monkeypatch, ["steam-leaderboard"])
    assert captured["my_id"] == _MY_ID


# ── Steam ID resolution ───────────────────────────────────────────────────────


def test_main_uses_session_id_when_my_id_not_set(monkeypatch, capsys):
    _run(monkeypatch, ["steam-leaderboard"], my_id=None, session_id=_MY_ID)
    # if it reached build_leaderboard, no error was printed
    assert "STEAM_ID" not in capsys.readouterr().out


def test_main_prints_error_when_no_steam_id(monkeypatch, capsys):
    monkeypatch.setattr(leaderboard_cli, "API_KEY", "REAL_KEY")
    monkeypatch.setattr(leaderboard_cli, "get_my_id", lambda **_: None)
    monkeypatch.setattr(sys, "argv", ["steam-leaderboard"])
    leaderboard_cli.main()
    assert "STEAM_ID" in capsys.readouterr().out
