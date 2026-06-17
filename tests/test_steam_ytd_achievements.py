import steam_ytd_achievements as sya


def test_resolve_friends_with_numeric_ids():
    result = sya.resolve_friends(["76561198001234567", "76561198009876543"])
    assert result == ["76561198001234567", "76561198009876543"]


def test_resolve_friends_empty():
    assert sya.resolve_friends([]) == []


def test_resolve_friends_mixed_calls_vanity(monkeypatch):
    monkeypatch.setattr(sya, "resolve_vanity_url", lambda v: "76561198000000001")
    assert sya.resolve_friends(["somevanity"]) == ["76561198000000001"]


def test_resolve_friends_skips_unresolvable_vanity(monkeypatch):
    monkeypatch.setattr(sya, "resolve_vanity_url", lambda v: None)
    assert sya.resolve_friends(["ghostuser"]) == []


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


def test_friends_override_env_parsing():
    raw = " name1 , name2 ,, name3 "
    result = [f.strip() for f in raw.split(",") if f.strip()]
    assert result == ["name1", "name2", "name3"]
