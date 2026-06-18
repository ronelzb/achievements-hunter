from unittest.mock import MagicMock

from steam_tracker import steam_http

# ── auth_post ─────────────────────────────────────────────────────────────────


def test_auth_post_constructs_correct_url(monkeypatch):
    mock_post = MagicMock()
    monkeypatch.setattr(steam_http.requests, "post", mock_post)
    steam_http.auth_post("BeginAuthSessionViaCredentials", data={"foo": "bar"})
    url = mock_post.call_args.args[0]
    assert url == f"{steam_http.AUTH_API}/BeginAuthSessionViaCredentials/v1"


def test_auth_post_passes_data_and_timeout(monkeypatch):
    mock_post = MagicMock()
    monkeypatch.setattr(steam_http.requests, "post", mock_post)
    steam_http.auth_post("PollAuthSessionStatus", data={"client_id": "x"}, timeout=30)
    assert mock_post.call_args.kwargs["data"] == {"client_id": "x"}
    assert mock_post.call_args.kwargs["timeout"] == 30


# ── get_authed ────────────────────────────────────────────────────────────────


def test_get_authed_uses_access_token_not_api_key(mock_http):
    mock_http.return_value = MagicMock(status_code=200)
    mock_http.return_value.json.return_value = {"result": "ok"}
    steam_http.get_authed(
        "IPlayerService/GetOwnedGames/v1", {"steamid": "123"}, access_token="mytoken"
    )
    params = mock_http.call_args.kwargs["params"]
    assert params.get("access_token") == "mytoken"
    assert "key" not in params


def test_get_authed_retries_on_500(mock_http):
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"result": "ok"}
    mock_http.side_effect = [MagicMock(status_code=500, text="err"), ok]
    assert steam_http.get_authed("endpoint", {}, access_token="tok") == {"result": "ok"}


def test_get_authed_returns_none_on_403(mock_http):
    mock_http.return_value = MagicMock(status_code=403, text="Forbidden")
    assert steam_http.get_authed("endpoint", {}, access_token="tok") is None
    assert mock_http.call_count == 1


# ── get ───────────────────────────────────────────────────────────────────────


def test_get_retries_on_500_and_succeeds(mock_http):
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"result": "ok"}
    mock_http.side_effect = [MagicMock(status_code=500, text="error"), ok]
    assert steam_http.get("endpoint", {}) == {"result": "ok"}


def test_get_exhausts_retries_on_persistent_500(mock_http):
    mock_http.return_value = MagicMock(status_code=500, text="err")
    assert steam_http.get("endpoint", {}) is None


def test_get_does_not_retry_on_4xx(mock_http):
    mock_http.return_value = MagicMock(status_code=403, text="Forbidden")
    assert steam_http.get("endpoint", {}) is None
    assert mock_http.call_count == 1  # no retries for deterministic client errors


def test_get_sets_last_status_on_error(mock_http):
    mock_http.return_value = MagicMock(status_code=403, text="err")
    steam_http._tls.last_status = None
    steam_http.get("endpoint", {})
    assert steam_http._tls.last_status == 403
