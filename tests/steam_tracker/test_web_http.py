"""Tests for web_http.py.

requests.get is monkeypatched so tests run fully offline.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import requests

from steam_tracker import web_http
from steam_tracker.web_http import fetch_url


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# ── fetch_url ─────────────────────────────────────────────────────────────────


def test_fetch_url_returns_response_text(monkeypatch):
    monkeypatch.setattr(
        web_http.requests, "get", MagicMock(return_value=_mock_response("hello"))
    )
    assert fetch_url("https://example.com") == "hello"


def test_fetch_url_returns_none_on_non_200(monkeypatch):
    monkeypatch.setattr(
        web_http.requests,
        "get",
        MagicMock(return_value=_mock_response("", status_code=404)),
    )
    assert fetch_url("https://example.com") is None


def test_fetch_url_returns_none_on_request_exception(monkeypatch):
    monkeypatch.setattr(
        web_http.requests,
        "get",
        MagicMock(side_effect=requests.RequestException("timeout")),
    )
    assert fetch_url("https://example.com") is None


def test_fetch_url_prints_debug_on_non_200(monkeypatch, capsys):
    monkeypatch.setattr(
        web_http.requests,
        "get",
        MagicMock(return_value=_mock_response("", status_code=403)),
    )
    fetch_url("https://example.com", True)
    assert "[debug]" in capsys.readouterr().out


def test_fetch_url_prints_debug_on_exception(monkeypatch, capsys):
    monkeypatch.setattr(
        web_http.requests,
        "get",
        MagicMock(side_effect=requests.RequestException("connection refused")),
    )
    fetch_url("https://example.com", True)
    assert "[debug]" in capsys.readouterr().out


def test_fetch_url_sends_user_agent_header(monkeypatch):
    mock_get = MagicMock(return_value=_mock_response("ok"))
    monkeypatch.setattr(web_http.requests, "get", mock_get)
    fetch_url("https://example.com", True)
    _, kwargs = mock_get.call_args
    assert "User-Agent" in kwargs.get("headers", {})
