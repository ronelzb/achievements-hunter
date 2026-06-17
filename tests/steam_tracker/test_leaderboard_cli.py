from steam_tracker import leaderboard_cli

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
