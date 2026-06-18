import base64
import json
import sys
from unittest.mock import MagicMock

import pytest
import rsa as rsa_lib

from steam_tracker import steam_auth

# ── shared stubs ──────────────────────────────────────────────────────────────

_RSA_STUB = {
    "publickey_mod": "deadbeef",
    "publickey_exp": "010001",
    "timestamp": "ts123",
}
_BEGIN_AUTH_RESULT = {
    "client_id": "client123",
    "request_id": "cmVxdWVzdA==",
    "steamid": "76561198000000000",
    "interval": 0.0,
    "allowed_confirmations": [],
}
_COOKIE_VALUE = "76561198000000000||securetoken"


def _stub_login_helpers(monkeypatch) -> None:
    """Stubs the full login helper chain for orchestration tests."""
    monkeypatch.setattr(steam_auth, "get_rsa_key", MagicMock(return_value=_RSA_STUB))
    monkeypatch.setattr(steam_auth, "encrypt_password", MagicMock(return_value="enc"))
    monkeypatch.setattr(
        steam_auth, "begin_auth", MagicMock(return_value=_BEGIN_AUTH_RESULT)
    )
    monkeypatch.setattr(steam_auth, "_select_and_submit_guard", MagicMock())
    monkeypatch.setattr(
        steam_auth, "poll_auth_session", MagicMock(return_value="refresh123")
    )
    monkeypatch.setattr(
        steam_auth, "finalize_session", MagicMock(return_value=_COOKIE_VALUE)
    )


# ── load_session ──────────────────────────────────────────────────────────────


def test_load_session_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(steam_auth.keyring, "get_password", lambda *_: None)
    assert steam_auth.load_session() is None


def test_load_session_returns_stored_value(monkeypatch):
    monkeypatch.setattr(steam_auth.keyring, "get_password", lambda *_: "token123")
    assert steam_auth.load_session() == "token123"


# ── save_session ──────────────────────────────────────────────────────────────


def test_save_session_stores_with_correct_service_and_key(monkeypatch):
    captured = []
    monkeypatch.setattr(
        steam_auth.keyring,
        "set_password",
        lambda service, user, value: captured.append((service, user, value)),
    )
    steam_auth.save_session("mysession")
    assert captured == [("achievements-hunter", "steamLoginSecure", "mysession")]


# ── load_refresh_token / save_refresh_token ───────────────────────────────────


def test_load_refresh_token_returns_stored_value(monkeypatch):
    monkeypatch.setattr(
        steam_auth.keyring,
        "get_password",
        lambda _, usr: "rt123" if usr == "steamRefreshToken" else None,
    )
    assert steam_auth.load_refresh_token() == "rt123"


def test_load_refresh_token_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(steam_auth.keyring, "get_password", lambda *_: None)
    assert steam_auth.load_refresh_token() is None


def test_save_refresh_token_stores_with_correct_key(monkeypatch):
    captured = []
    monkeypatch.setattr(
        steam_auth.keyring,
        "set_password",
        lambda svc, usr, val: captured.append((svc, usr, val)),
    )
    steam_auth.save_refresh_token("myrefresh")
    assert captured == [("achievements-hunter", "steamRefreshToken", "myrefresh")]


# ── logout ────────────────────────────────────────────────────────────────────


def test_logout_deletes_both_keyring_entries(monkeypatch):
    deleted = []
    monkeypatch.setattr(
        steam_auth.keyring, "delete_password", lambda _, usr: deleted.append(usr)
    )
    steam_auth.logout()
    assert "steamLoginSecure" in deleted
    assert "steamRefreshToken" in deleted


def test_logout_handles_missing_entries_gracefully(monkeypatch):
    def raise_error(_, __):
        raise Exception("not found")

    monkeypatch.setattr(steam_auth.keyring, "delete_password", raise_error)
    steam_auth.logout()  # should not raise


# ── _token_expiry ─────────────────────────────────────────────────────────────
# JWT format edge cases (plain strings, malformed base64) live in test_utils.py.
# These tests cover what _token_expiry adds: extracting the exp int from a payload.


def _make_cookie(exp: int) -> str:
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    )
    return f"76561198000000000||header.{payload}.sig"


def test_token_expiry_extracts_exp_from_valid_cookie():
    assert steam_auth._token_expiry(_make_cookie(9999999999)) == 9999999999


def test_token_expiry_returns_none_when_exp_missing():
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps({"iss": "steam"}).encode())
        .decode()
        .rstrip("=")
    )
    assert steam_auth._token_expiry(f"76561198000000000||h.{payload_b64}.s") is None


def test_token_expiry_returns_none_for_non_jwt_cookie():
    assert steam_auth._token_expiry("76561198000000000||notajwt") is None


# ── validate_session ──────────────────────────────────────────────────────────


def test_validate_session_true_when_redirected_to_profile(monkeypatch, mock_response):
    monkeypatch.setattr(
        steam_auth,
        "community_get",
        MagicMock(
            return_value=mock_response(
                url="https://steamcommunity.com/profiles/76561198000000000/"
            )
        ),
    )
    assert steam_auth.validate_session("token") is True


def test_validate_session_false_when_redirected_to_login(monkeypatch, mock_response):
    monkeypatch.setattr(
        steam_auth,
        "community_get",
        MagicMock(
            return_value=mock_response(url="https://steamcommunity.com/login/home/")
        ),
    )
    assert steam_auth.validate_session("token") is False


def test_validate_session_false_on_network_error(monkeypatch):
    monkeypatch.setattr(steam_auth, "community_get", MagicMock(return_value=None))
    assert steam_auth.validate_session("token") is False


def test_validate_session_false_when_token_expired(monkeypatch):
    monkeypatch.setattr(steam_auth.time, "time", lambda: 2_000_000_000.0)
    cookie = _make_cookie(exp=1_000_000_000)
    assert steam_auth.validate_session(cookie) is False


def test_validate_session_skips_network_when_token_expired(monkeypatch):
    monkeypatch.setattr(steam_auth.time, "time", lambda: 2_000_000_000.0)
    network = MagicMock()
    monkeypatch.setattr(steam_auth, "community_get", network)
    steam_auth.validate_session(_make_cookie(exp=1_000_000_000))
    network.assert_not_called()


# ── get_rsa_key ───────────────────────────────────────────────────────────────


def test_get_rsa_key_returns_parsed_json(monkeypatch, mock_response):
    rsa_payload = {
        "publickey_mod": "abcdef",
        "publickey_exp": "010001",
        "timestamp": "12345678",
    }
    monkeypatch.setattr(
        steam_auth,
        "community_post",
        MagicMock(return_value=mock_response(json_data=rsa_payload)),
    )
    result = steam_auth.get_rsa_key("testuser")
    assert result["publickey_mod"] == "abcdef"
    assert result["timestamp"] == "12345678"


# ── encrypt_password ──────────────────────────────────────────────────────────


def test_encrypt_password_returns_valid_base64():
    (pub_key, _) = rsa_lib.newkeys(512)
    mod = format(pub_key.n, "x")
    exp = format(pub_key.e, "x")
    result = steam_auth.encrypt_password("hunter2", mod, exp)
    decoded = base64.b64decode(result)
    assert len(decoded) > 0


# ── _select_and_submit_guard ──────────────────────────────────────────────────


def test_select_guard_mobile_only_prints_message(monkeypatch, capsys):
    monkeypatch.setattr(steam_auth, "submit_guard_code", MagicMock())
    steam_auth._select_and_submit_guard({4}, "cid", "sid")
    assert "Steam mobile app" in capsys.readouterr().out


def test_select_guard_totp_only_prompts_and_submits(monkeypatch):
    submit_mock = MagicMock()
    monkeypatch.setattr(steam_auth, "submit_guard_code", submit_mock)
    monkeypatch.setattr("builtins.input", lambda _: "ABCDE")
    steam_auth._select_and_submit_guard({3}, "cid", "sid")
    submit_mock.assert_called_once_with("cid", "sid", "ABCDE", code_type=3)


def test_select_guard_email_only_prompts_and_submits(monkeypatch):
    submit_mock = MagicMock()
    monkeypatch.setattr(steam_auth, "submit_guard_code", submit_mock)
    monkeypatch.setattr("builtins.input", lambda _: "EMAIL1")
    steam_auth._select_and_submit_guard({2}, "cid", "sid")
    submit_mock.assert_called_once_with("cid", "sid", "EMAIL1", code_type=2)


def test_select_guard_shows_menu_when_multiple_options(monkeypatch, capsys):
    monkeypatch.setattr(steam_auth, "submit_guard_code", MagicMock())
    monkeypatch.setattr("builtins.input", lambda _: "1")
    steam_auth._select_and_submit_guard({3, 4}, "cid", "sid")
    out = capsys.readouterr().out
    assert "choose a method" in out
    assert "Tap Approve" in out
    assert "authenticator code" in out


def test_select_guard_multi_user_picks_totp(monkeypatch):
    submit_mock = MagicMock()
    monkeypatch.setattr(steam_auth, "submit_guard_code", submit_mock)
    inputs = iter(["2", "MYCODE"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    steam_auth._select_and_submit_guard({3, 4}, "cid", "sid")
    submit_mock.assert_called_once_with("cid", "sid", "MYCODE", code_type=3)


def test_select_guard_invalid_input_loops_until_valid(monkeypatch, capsys):
    monkeypatch.setattr(steam_auth, "submit_guard_code", MagicMock())
    inputs = iter(["x", "99", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    steam_auth._select_and_submit_guard({3, 4}, "cid", "sid")
    assert "Steam mobile app" in capsys.readouterr().out


def test_select_guard_blank_input_defaults_to_first_option(monkeypatch, capsys):
    monkeypatch.setattr(steam_auth, "submit_guard_code", MagicMock())
    monkeypatch.setattr("builtins.input", lambda _: "")
    steam_auth._select_and_submit_guard({3, 4}, "cid", "sid")
    assert "Steam mobile app" in capsys.readouterr().out


def test_select_guard_no_options_does_nothing(monkeypatch):
    submit_mock = MagicMock()
    monkeypatch.setattr(steam_auth, "submit_guard_code", submit_mock)
    steam_auth._select_and_submit_guard(set(), "cid", "sid")
    submit_mock.assert_not_called()


# ── login (orchestration) ─────────────────────────────────────────────────────


def test_login_returns_cookie_on_success(monkeypatch):
    _stub_login_helpers(monkeypatch)
    assert steam_auth.login("user", "pass") == _COOKIE_VALUE


def test_login_saves_refresh_token(monkeypatch):
    _stub_login_helpers(monkeypatch)
    saved = []
    monkeypatch.setattr(steam_auth, "save_refresh_token", lambda t: saved.append(t))
    steam_auth.login("user", "pass")
    assert saved == ["refresh123"]


def test_login_passes_conf_types_to_select_guard(monkeypatch):
    _stub_login_helpers(monkeypatch)
    select_mock = MagicMock()
    monkeypatch.setattr(steam_auth, "_select_and_submit_guard", select_mock)
    monkeypatch.setattr(
        steam_auth,
        "begin_auth",
        MagicMock(
            return_value={
                **_BEGIN_AUTH_RESULT,
                "allowed_confirmations": [
                    {"confirmation_type": 3},
                    {"confirmation_type": 4},
                ],
            }
        ),
    )
    steam_auth.login("user", "pass")
    called_conf_types = select_mock.call_args.args[0]
    assert called_conf_types == {3, 4}


def test_login_raises_on_failed_credentials(monkeypatch):
    monkeypatch.setattr(steam_auth, "get_rsa_key", MagicMock(return_value=_RSA_STUB))
    monkeypatch.setattr(steam_auth, "encrypt_password", MagicMock(return_value="enc"))
    monkeypatch.setattr(
        steam_auth,
        "begin_auth",
        MagicMock(side_effect=RuntimeError("Invalid password.")),
    )
    with pytest.raises(RuntimeError, match="Invalid password"):
        steam_auth.login("user", "wrongpass")


# ── main ──────────────────────────────────────────────────────────────────────


def test_main_skips_login_when_session_is_valid(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["steam-login", "--login"])
    monkeypatch.setattr(steam_auth, "load_session", lambda: "existingtoken")
    monkeypatch.setattr(steam_auth, "validate_session", MagicMock(return_value=True))
    steam_auth.main()
    assert "Already logged in" in capsys.readouterr().out


def test_main_saves_cookie_after_successful_login(monkeypatch, capsys):
    saved = []
    monkeypatch.setattr(sys, "argv", ["steam-login", "--login"])
    monkeypatch.setattr(steam_auth, "load_session", lambda: None)
    monkeypatch.setattr(steam_auth, "login", MagicMock(return_value="steamid||token"))
    monkeypatch.setattr(steam_auth, "save_session", lambda cookie: saved.append(cookie))
    monkeypatch.setattr("builtins.input", lambda _: "myuser")
    monkeypatch.setattr(steam_auth.getpass, "getpass", lambda _: "mypassword")
    steam_auth.main()
    assert saved == ["steamid||token"]
    assert "Login successful" in capsys.readouterr().out


def test_main_prints_error_and_exits_on_login_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["steam-login", "--login"])
    monkeypatch.setattr(steam_auth, "load_session", lambda: None)
    monkeypatch.setattr(
        steam_auth, "login", MagicMock(side_effect=RuntimeError("Bad credentials."))
    )
    monkeypatch.setattr("builtins.input", lambda _: "myuser")
    monkeypatch.setattr(steam_auth.getpass, "getpass", lambda _: "wrongpass")
    with pytest.raises(SystemExit) as exc_info:
        steam_auth.main()
    assert exc_info.value.code == 1
    assert "Bad credentials" in capsys.readouterr().out


def test_main_logout_clears_session_and_prints_message(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["steam-login", "--logout"])
    monkeypatch.setattr(steam_auth, "logout", MagicMock())
    steam_auth.main()
    assert "Logged out" in capsys.readouterr().out


def test_main_requires_login_or_logout_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["steam-login"])
    with pytest.raises(SystemExit) as exc_info:
        steam_auth.main()
    assert exc_info.value.code == 2  # argparse error exit code
