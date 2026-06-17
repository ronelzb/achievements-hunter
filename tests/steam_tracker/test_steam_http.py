from unittest.mock import MagicMock

from steam_tracker import steam_http


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
