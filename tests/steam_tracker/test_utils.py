import base64
import json

from steam_tracker.utils import decode_token, game_slug, truncate


def _make_jwt_cookie(payload: dict) -> str:
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"76561198000000000||header.{payload_b64}.sig"


# ── decode_token ──────────────────────────────────────────────────────────────


def test_decode_token_returns_full_payload():
    cookie = _make_jwt_cookie({"exp": 9999999999, "iss": "steam"})
    assert decode_token(cookie) == {"exp": 9999999999, "iss": "steam"}


def test_decode_token_works_when_payload_length_multiple_of_four():
    # Exercises the (-len) % 4 == 0 padding path that the old formula broke
    payload = {"a": "b"}
    raw_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    # Pad the payload string to a length that is a multiple of 4
    while len(raw_b64) % 4 != 0:
        payload["_"] = payload.get("_", "") + "x"
        raw_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
    cookie = f"76561198000000000||header.{raw_b64}.sig"
    result = decode_token(cookie)
    assert result is not None
    assert result["a"] == "b"


def test_decode_token_works_for_raw_jwt_without_prefix():
    payload = {"aud": ["web", "mobile"], "sub": "76561198000000000"}
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    raw_jwt = f"header.{payload_b64}.sig"
    assert decode_token(raw_jwt) == payload


def test_decode_token_returns_none_for_plain_string():
    assert decode_token("76561198000000000||notajwt") is None


def test_decode_token_returns_none_for_malformed_base64():
    assert decode_token("76561198000000000||header.!!!invalid!!!.sig") is None


def test_decode_token_returns_none_for_empty_cookie():
    assert decode_token("") is None


def test_decode_token_returns_none_for_missing_separator():
    assert decode_token("plaintoken") is None


# ── truncate ──────────────────────────────────────────────────────────────────


def test_truncate_returns_string_unchanged_when_within_width():
    assert truncate("hello", 10) == "hello"


def test_truncate_returns_string_unchanged_when_exactly_at_width():
    assert truncate("hello", 5) == "hello"


def test_truncate_cuts_and_appends_ellipsis_when_over_width():
    assert truncate("hello world", 8) == "hello w…"


def test_truncate_result_length_equals_width():
    result = truncate("abcdefghij", 6)
    assert len(result) == 6


def test_truncate_empty_string():
    assert truncate("", 5) == ""


# ── game_slug ─────────────────────────────────────────────────────────────────


def test_game_slug_lowercases():
    assert game_slug("Portal").startswith("p")


def test_game_slug_replaces_spaces():
    assert " " not in game_slug("The Evil Within")


def test_game_slug_replaces_special_chars():
    slug = game_slug("Demon's Souls")
    assert "'" not in slug
    assert slug == "demon-s-souls"


def test_game_slug_no_leading_trailing_dashes():
    slug = game_slug("  ---Game---  ")
    assert not slug.startswith("-")
    assert not slug.endswith("-")


def test_game_slug_numbers_preserved():
    assert "2" in game_slug("Portal 2")
