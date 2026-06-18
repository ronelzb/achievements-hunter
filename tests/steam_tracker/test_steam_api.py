import base64
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

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


# ── generate_api_access_token ─────────────────────────────────────────────────


def _make_refresh_token(aud: list[str]) -> str:
    payload = (
        base64.urlsafe_b64encode(json.dumps({"aud": aud, "sub": _STEAM_ID}).encode())
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.sig"


def test_generate_api_access_token_raises_on_missing_mobile_aud():
    token = _make_refresh_token(["web", "renew", "derive"])
    with pytest.raises(RuntimeError, match=r"mobile.*audience"):
        steam_api.generate_api_access_token(token, _STEAM_ID)


def test_generate_api_access_token_returns_token(monkeypatch):
    mock = MagicMock()
    mock.return_value.json.return_value = {"response": {"access_token": "myapitoken"}}
    monkeypatch.setattr(steam_api, "auth_post", mock)
    access_token, new_refresh = steam_api.generate_api_access_token(
        "refresh123", _STEAM_ID
    )
    assert access_token == "myapitoken"
    assert new_refresh is None


def test_generate_api_access_token_returns_rotated_refresh_token(monkeypatch):
    mock = MagicMock()
    mock.return_value.json.return_value = {
        "response": {"access_token": "tok", "refresh_token": "newrt"}
    }
    monkeypatch.setattr(steam_api, "auth_post", mock)
    _, new_refresh = steam_api.generate_api_access_token("refresh123", _STEAM_ID)
    assert new_refresh == "newrt"


def test_generate_api_access_token_sends_renew_flag(monkeypatch):
    mock = MagicMock()
    mock.return_value.json.return_value = {"response": {"access_token": "tok"}}
    monkeypatch.setattr(steam_api, "auth_post", mock)
    steam_api.generate_api_access_token("refresh123", _STEAM_ID)
    assert mock.call_args.kwargs["data"]["renew_refresh_token"] == 1


def test_generate_api_access_token_raises_on_missing_token(monkeypatch):
    mock = MagicMock()
    mock.return_value.json.return_value = {"response": {}}
    monkeypatch.setattr(steam_api, "auth_post", mock)
    with pytest.raises(RuntimeError, match="returned no access_token"):
        steam_api.generate_api_access_token("bad_refresh", _STEAM_ID)


# ── get_owned_games_auth ──────────────────────────────────────────────────────


def test_get_owned_games_auth_returns_games_on_success(monkeypatch):
    monkeypatch.setattr(
        steam_api,
        "get_authed",
        MagicMock(
            return_value={
                "response": {"games": [{"appid": 440, "playtime_forever": 120}]}
            }
        ),
    )
    result = steam_api.get_owned_games_auth("76561198000000000", "rawjwt")
    assert result == [{"appid": 440, "playtime_forever": 120}]


def test_get_owned_games_auth_passes_token_as_access_token(monkeypatch):
    mock = MagicMock(return_value={"response": {"games": []}})
    monkeypatch.setattr(steam_api, "get_authed", mock)
    steam_api.get_owned_games_auth("76561198000000000", "my.api.token")
    assert mock.call_args.kwargs["access_token"] == "my.api.token"


def test_get_owned_games_auth_returns_empty_on_api_failure(monkeypatch):
    monkeypatch.setattr(steam_api, "get_authed", MagicMock(return_value=None))
    assert steam_api.get_owned_games_auth("76561198000000000", "rawjwt") == []


# ── IAuthenticationService ────────────────────────────────────────────────────

_COOKIE_VALUE = "76561198000000000||securetoken"
_STEAM_ID = "76561198000000000"


def test_begin_auth_returns_data_on_success(monkeypatch):
    mock = MagicMock()
    mock.return_value.json.return_value = {
        "response": {"client_id": "cid1", "request_id": "rid1", "steamid": _STEAM_ID}
    }
    monkeypatch.setattr(steam_api, "auth_post", mock)
    result = steam_api.begin_auth("user", "encpass", "ts")
    assert result["client_id"] == "cid1"


def test_begin_auth_raises_on_missing_client_id(monkeypatch):
    mock = MagicMock()
    mock.return_value.json.return_value = {
        "response": {"error_message": "Invalid password."}
    }
    monkeypatch.setattr(steam_api, "auth_post", mock)
    with pytest.raises(RuntimeError, match="Invalid password"):
        steam_api.begin_auth("user", "badpass", "ts")


def test_poll_auth_session_returns_token_on_first_response(monkeypatch):
    mock = MagicMock()
    mock.return_value.json.return_value = {"response": {"refresh_token": "tok123"}}
    monkeypatch.setattr(steam_api, "auth_post", mock)
    monkeypatch.setattr(steam_api.time, "sleep", MagicMock())
    assert steam_api.poll_auth_session("cid", "rid", interval=0.0) == "tok123"


def test_poll_auth_session_raises_on_timeout(monkeypatch):
    mock = MagicMock()
    mock.return_value.json.return_value = {"response": {}}
    monkeypatch.setattr(steam_api, "auth_post", mock)
    monkeypatch.setattr(steam_api.time, "sleep", MagicMock())
    with pytest.raises(RuntimeError, match="timed out"):
        steam_api.poll_auth_session("cid", "rid", interval=0.0)


def _make_session_mock(finalize_json: dict, transfer_cookie: str | None) -> MagicMock:
    finalize_mock = MagicMock()
    finalize_mock.json.return_value = finalize_json
    transfer_mock = MagicMock()
    transfer_mock.cookies.get.return_value = transfer_cookie

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.post.side_effect = [finalize_mock, transfer_mock]
    session.cookies.get.return_value = None
    return session


def test_finalize_session_extracts_cookie(monkeypatch):
    session = _make_session_mock(
        finalize_json={
            "transfer_info": [
                {
                    "url": "https://steamcommunity.com/login/settoken",
                    "params": {"nonce": "n", "auth": "a"},
                }
            ]
        },
        transfer_cookie=_COOKIE_VALUE,
    )
    monkeypatch.setattr(steam_api.requests, "Session", MagicMock(return_value=session))
    monkeypatch.setattr(steam_api.secrets, "token_hex", lambda _: "sess123")
    assert steam_api.finalize_session("refresh123", _STEAM_ID) == _COOKIE_VALUE
    _, transfer_call = session.post.call_args_list
    assert transfer_call.kwargs["data"]["steamID"] == _STEAM_ID
    assert transfer_call.kwargs.get("allow_redirects") is False


def test_finalize_session_raises_when_cookie_absent(monkeypatch):
    session = _make_session_mock(
        finalize_json={
            "transfer_info": [
                {"url": "https://steamcommunity.com/login/settoken", "params": {}}
            ]
        },
        transfer_cookie=None,
    )
    monkeypatch.setattr(steam_api.requests, "Session", MagicMock(return_value=session))
    monkeypatch.setattr(steam_api.secrets, "token_hex", lambda _: "sess123")
    with pytest.raises(RuntimeError, match="steamLoginSecure cookie not set"):
        steam_api.finalize_session("refresh123", _STEAM_ID)
