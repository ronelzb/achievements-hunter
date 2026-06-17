import base64
from unittest.mock import MagicMock

import pytest
import rsa as rsa_lib

from steam_tracker import steam_login

# ── shared stubs ──────────────────────────────────────────────────────────────

_RSA_STUB = {
    "publickey_mod": "deadbeef",
    "publickey_exp": "010001",
    "timestamp": "ts123",
}
_TRANSFER_PARAMS = {
    "steamid": "76561198000000000",
    "token_secure": "securetoken",
}
_LOGIN_SUCCESS = {"login_complete": True, "transfer_parameters": _TRANSFER_PARAMS}


def _stub_crypto(monkeypatch) -> None:
    """Stubs RSA key fetch and password encryption for login orchestration tests."""
    monkeypatch.setattr(steam_login, "get_rsa_key", MagicMock(return_value=_RSA_STUB))
    monkeypatch.setattr(steam_login, "encrypt_password", MagicMock(return_value="enc"))


# ── load_session ──────────────────────────────────────────────────────────────


def test_load_session_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(steam_login.keyring, "get_password", lambda *_: None)
    assert steam_login.load_session() is None


def test_load_session_returns_stored_value(monkeypatch):
    monkeypatch.setattr(steam_login.keyring, "get_password", lambda *_: "token123")
    assert steam_login.load_session() == "token123"


# ── save_session ──────────────────────────────────────────────────────────────


def test_save_session_stores_with_correct_service_and_key(monkeypatch):
    captured = []
    monkeypatch.setattr(
        steam_login.keyring,
        "set_password",
        lambda service, user, value: captured.append((service, user, value)),
    )
    steam_login.save_session("mysession")
    assert captured == [("achievements-hunter", "steamLoginSecure", "mysession")]


# ── validate_session ──────────────────────────────────────────────────────────


def test_validate_session_true_when_redirected_to_profile(monkeypatch, mock_response):
    monkeypatch.setattr(
        steam_login,
        "community_get",
        MagicMock(
            return_value=mock_response(
                url="https://steamcommunity.com/profiles/76561198000000000/"
            )
        ),
    )
    assert steam_login.validate_session("token") is True


def test_validate_session_false_when_redirected_to_login(monkeypatch, mock_response):
    monkeypatch.setattr(
        steam_login,
        "community_get",
        MagicMock(
            return_value=mock_response(url="https://steamcommunity.com/login/home/")
        ),
    )
    assert steam_login.validate_session("token") is False


def test_validate_session_false_on_network_error(monkeypatch):
    monkeypatch.setattr(steam_login, "community_get", MagicMock(return_value=None))
    assert steam_login.validate_session("token") is False


# ── get_rsa_key ───────────────────────────────────────────────────────────────


def test_get_rsa_key_returns_parsed_json(monkeypatch, mock_response):
    rsa_payload = {
        "publickey_mod": "abcdef",
        "publickey_exp": "010001",
        "timestamp": "12345678",
    }
    monkeypatch.setattr(
        steam_login,
        "community_post",
        MagicMock(return_value=mock_response(json_data=rsa_payload)),
    )
    result = steam_login.get_rsa_key("testuser")
    assert result["publickey_mod"] == "abcdef"
    assert result["timestamp"] == "12345678"


# ── encrypt_password ──────────────────────────────────────────────────────────


def test_encrypt_password_returns_valid_base64():
    (pub_key, _) = rsa_lib.newkeys(512)
    mod = format(pub_key.n, "x")
    exp = format(pub_key.e, "x")
    result = steam_login.encrypt_password("hunter2", mod, exp)
    decoded = base64.b64decode(result)
    assert len(decoded) > 0


# ── do_login ──────────────────────────────────────────────────────────────────


def test_do_login_returns_parsed_json(monkeypatch, mock_response):
    login_payload = {
        "success": True,
        "login_complete": True,
        "transfer_parameters": _TRANSFER_PARAMS,
    }
    monkeypatch.setattr(
        steam_login,
        "community_post",
        MagicMock(return_value=mock_response(json_data=login_payload)),
    )
    monkeypatch.setattr(steam_login.time, "time", lambda: 1000.0)
    result = steam_login.do_login("user", "encpass", "ts")
    assert result["login_complete"] is True


def test_do_login_sends_guard_code_in_payload(monkeypatch, mock_response):
    mock_post = MagicMock(
        return_value=mock_response(
            json_data={"login_complete": True, "transfer_parameters": {}}
        )
    )
    monkeypatch.setattr(steam_login, "community_post", mock_post)
    monkeypatch.setattr(steam_login.time, "time", lambda: 1000.0)
    steam_login.do_login("user", "encpass", "ts", guard_code="ABCDE")
    assert mock_post.call_args.kwargs["data"]["twofactorcode"] == "ABCDE"


def test_do_login_sends_email_code_in_payload(monkeypatch, mock_response):
    mock_post = MagicMock(
        return_value=mock_response(
            json_data={"login_complete": True, "transfer_parameters": {}}
        )
    )
    monkeypatch.setattr(steam_login, "community_post", mock_post)
    monkeypatch.setattr(steam_login.time, "time", lambda: 1000.0)
    steam_login.do_login("user", "encpass", "ts", email_code="XY123")
    assert mock_post.call_args.kwargs["data"]["emailauth"] == "XY123"


# ── login (orchestration) ─────────────────────────────────────────────────────


def test_login_returns_formatted_cookie_on_success(monkeypatch):
    _stub_crypto(monkeypatch)
    monkeypatch.setattr(steam_login, "do_login", MagicMock(return_value=_LOGIN_SUCCESS))
    cookie = steam_login.login("user", "pass")
    assert cookie == "76561198000000000||securetoken"


def test_login_prompts_for_mobile_guard_code(monkeypatch):
    _stub_crypto(monkeypatch)
    monkeypatch.setattr(
        steam_login,
        "do_login",
        MagicMock(side_effect=[{"requires_twofactor": True}, _LOGIN_SUCCESS]),
    )
    monkeypatch.setattr("builtins.input", lambda _: "GUARD1")
    cookie = steam_login.login("user", "pass")
    assert cookie == "76561198000000000||securetoken"


def test_login_prompts_for_email_guard_code(monkeypatch):
    _stub_crypto(monkeypatch)
    monkeypatch.setattr(
        steam_login,
        "do_login",
        MagicMock(
            side_effect=[
                {"emailauth_needed": True, "emaildomain": "gmail.com"},
                _LOGIN_SUCCESS,
            ]
        ),
    )
    monkeypatch.setattr("builtins.input", lambda _: "EMAIL1")
    cookie = steam_login.login("user", "pass")
    assert cookie == "76561198000000000||securetoken"


def test_login_raises_on_failed_credentials(monkeypatch):
    _stub_crypto(monkeypatch)
    monkeypatch.setattr(
        steam_login,
        "do_login",
        MagicMock(
            return_value={"login_complete": False, "message": "Invalid password."}
        ),
    )
    with pytest.raises(RuntimeError, match="Invalid password"):
        steam_login.login("user", "wrongpass")


# ── main ──────────────────────────────────────────────────────────────────────


def test_main_skips_login_when_session_is_valid(monkeypatch, capsys):
    monkeypatch.setattr(steam_login, "load_session", lambda: "existingtoken")
    monkeypatch.setattr(steam_login, "validate_session", lambda _: True)
    steam_login.main()
    assert "Already logged in" in capsys.readouterr().out


def test_main_saves_cookie_after_successful_login(monkeypatch, capsys):
    saved = []
    monkeypatch.setattr(steam_login, "load_session", lambda: None)
    monkeypatch.setattr(steam_login, "login", MagicMock(return_value="steamid||token"))
    monkeypatch.setattr(
        steam_login, "save_session", lambda cookie: saved.append(cookie)
    )
    monkeypatch.setattr("builtins.input", lambda _: "myuser")
    monkeypatch.setattr(steam_login.getpass, "getpass", lambda _: "mypassword")
    steam_login.main()
    assert saved == ["steamid||token"]
    assert "Login successful" in capsys.readouterr().out


def test_main_prints_error_and_exits_on_login_failure(monkeypatch, capsys):
    monkeypatch.setattr(steam_login, "load_session", lambda: None)
    monkeypatch.setattr(
        steam_login, "login", MagicMock(side_effect=RuntimeError("Bad credentials."))
    )
    monkeypatch.setattr("builtins.input", lambda _: "myuser")
    monkeypatch.setattr(steam_login.getpass, "getpass", lambda _: "wrongpass")
    with pytest.raises(SystemExit) as exc_info:
        steam_login.main()
    assert exc_info.value.code == 1
    assert "Bad credentials" in capsys.readouterr().out
