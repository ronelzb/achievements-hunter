"""
Tests for the parser hierarchy and SteamAchievementSchemaParser.

Coverage:
  - Parser/BytesParser: ABC enforcement and inheritance
  - SteamAchievementSchemaParser:
      - empty or invalid bytes → {}
      - flat 'stats' key (no app-id wrapper)
      - nested app-id wrapper
      - hidden achievement descriptions ARE included (the whole point)
      - entries without name or empty description are skipped
      - multiple achievements
"""

from __future__ import annotations

import inspect

import vdf

from steam_tracker.parser import BytesParser, Parser, SteamAchievementSchemaParser

# ── hierarchy ─────────────────────────────────────────────────────────────────


def test_parser_root_is_abstract():
    assert inspect.isabstract(Parser)


def test_bytes_parser_is_abstract():
    assert inspect.isabstract(BytesParser)


def test_bytes_parser_extends_parser():
    assert issubclass(BytesParser, Parser)


def test_steam_achievement_schema_parser_extends_bytes_parser():
    assert issubclass(SteamAchievementSchemaParser, BytesParser)


def test_steam_achievement_schema_parser_is_concrete():
    assert not inspect.isabstract(SteamAchievementSchemaParser)


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_vdf(stats: dict) -> bytes:
    """Wrap *stats* in a binary VDF structure matching Steam's flat layout."""
    return vdf.binary_dumps({"stats": stats})


def _make_ach(name: str, desc: str, *, hidden: str = "0") -> dict:
    return {
        "name": name,
        "display": {
            "name": {"english": name},
            "desc": {"english": desc},
            "hidden": hidden,
        },
    }


# ── empty / invalid input ─────────────────────────────────────────────────────


def test_empty_bytes_returns_empty():
    assert SteamAchievementSchemaParser().parse(b"") == {}


def test_invalid_bytes_returns_empty():
    assert SteamAchievementSchemaParser().parse(b"not valid vdf") == {}


def test_random_bytes_returns_empty():
    assert SteamAchievementSchemaParser().parse(bytes(range(256))) == {}


# ── flat layout (stats at top level) ─────────────────────────────────────────


def test_parse_single_achievement():
    raw = _make_vdf({"1": _make_ach("ACH_WIN", "Win a game.")})
    assert SteamAchievementSchemaParser().parse(raw) == {"ACH_WIN": "Win a game."}


def test_parse_multiple_achievements():
    raw = _make_vdf(
        {
            "1": _make_ach("ACH_WIN", "Win a game."),
            "2": _make_ach("ACH_LOSE", "Lose a game."),
        }
    )
    result = SteamAchievementSchemaParser().parse(raw)
    assert result == {"ACH_WIN": "Win a game.", "ACH_LOSE": "Lose a game."}


# ── hidden achievements ───────────────────────────────────────────────────────


def test_hidden_achievement_description_is_included():
    # This is the core gap: GetSchemaForGame returns empty desc for hidden=1,
    # but the local .bin file has the real description.
    raw = _make_vdf({"1": _make_ach("ACH_SECRET", "You found the secret!", hidden="1")})
    assert SteamAchievementSchemaParser().parse(raw) == {
        "ACH_SECRET": "You found the secret!"
    }


# ── bits-wrapped layout (e.g. Elden Ring) ────────────────────────────────────


def test_parse_bits_wrapped_achievement():
    raw = _make_vdf({"1": {"bits": {"0": _make_ach("ACH00", "Become Elden Lord.")}}})
    assert SteamAchievementSchemaParser().parse(raw) == {"ACH00": "Become Elden Lord."}


def test_parse_bits_wrapped_multiple():
    raw = _make_vdf(
        {
            "1": {"bits": {"0": _make_ach("ACH00", "First.")}},
            "2": {"bits": {"0": _make_ach("ACH01", "Second.")}},
        }
    )
    assert SteamAchievementSchemaParser().parse(raw) == {
        "ACH00": "First.",
        "ACH01": "Second.",
    }


def test_parse_bits_wrapped_hidden():
    raw = _make_vdf(
        {"1": {"bits": {"0": _make_ach("ACH_SECRET", "Hidden desc.", hidden="1")}}}
    )
    assert SteamAchievementSchemaParser().parse(raw) == {"ACH_SECRET": "Hidden desc."}


# ── nested app-id wrapper ─────────────────────────────────────────────────────


def test_parse_nested_app_id_wrapper():
    data = {"220": {"stats": {"1": _make_ach("ACH_WIN", "Win a game.")}}}
    raw = vdf.binary_dumps(data)
    assert SteamAchievementSchemaParser().parse(raw) == {"ACH_WIN": "Win a game."}


# ── skipped entries ───────────────────────────────────────────────────────────


def test_entry_with_empty_description_is_skipped():
    raw = _make_vdf({"1": _make_ach("ACH_NO_DESC", "")})
    assert SteamAchievementSchemaParser().parse(raw) == {}


def test_entry_without_name_is_skipped():
    raw = _make_vdf({"1": {"display": {"desc": {"english": "Some desc"}}}})
    assert SteamAchievementSchemaParser().parse(raw) == {}


def test_non_dict_stat_entry_is_skipped():
    raw = _make_vdf({"nAllStats": 1, "1": _make_ach("ACH_WIN", "Win a game.")})
    result = SteamAchievementSchemaParser().parse(raw)
    assert result == {"ACH_WIN": "Win a game."}
