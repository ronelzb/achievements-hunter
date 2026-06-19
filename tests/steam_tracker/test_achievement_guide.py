"""Tests for achievement_guide.py.

Network calls are eliminated by monkeypatching fetch_url so tests are fast
and fully offline.  HtmlParser, game_slug, and fetch_url are each tested
in their own modules (test_parser.py, test_utils.py, test_web_http.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from steam_tracker import achievement_guide
from steam_tracker.achievement_guide import (
    _fetch_powerpyx,
    _fetch_steam_guides,
    _fetch_truesteam,
    fetch_guide,
)
from steam_tracker.contracts import GuideContent

# ── _fetch_truesteam ──────────────────────────────────────────────────────────


def test_fetch_truesteam_returns_text_and_url(monkeypatch):
    monkeypatch.setattr(
        achievement_guide, "fetch_url", MagicMock(return_value="<p>Guide text</p>")
    )
    text, url = _fetch_truesteam("The Evil Within")
    assert "Guide text" in text
    assert "truesteamachievements.com" in url
    assert "the-evil-within" in url


def test_fetch_truesteam_uses_game_slug_in_url(monkeypatch):
    captured_urls: list[str] = []

    def _mock_fetch(url, *_):
        captured_urls.append(url)
        return "<p>text</p>"

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    _fetch_truesteam("Demon's Souls")
    assert captured_urls
    assert "demon-s-souls" in captured_urls[0]


def test_fetch_truesteam_returns_empty_on_network_failure(monkeypatch):
    monkeypatch.setattr(achievement_guide, "fetch_url", MagicMock(return_value=None))
    text, _ = _fetch_truesteam("The Evil Within")
    assert text == ""


def test_fetch_truesteam_caps_text_at_limit(monkeypatch):
    long_html = "<p>" + "x" * 100_000 + "</p>"
    monkeypatch.setattr(
        achievement_guide, "fetch_url", MagicMock(return_value=long_html)
    )
    text, _ = _fetch_truesteam("Game")
    assert len(text) <= achievement_guide._TEXT_LIMIT


# ── _fetch_powerpyx ───────────────────────────────────────────────────────────


def test_fetch_powerpyx_returns_text_and_url(monkeypatch):
    monkeypatch.setattr(
        achievement_guide, "fetch_url", MagicMock(return_value="<p>Guide</p>")
    )
    text, url = _fetch_powerpyx("The Evil Within")
    assert "Guide" in text
    assert "powerpyx.com" in url
    assert "the-evil-within" in url


def test_fetch_powerpyx_tries_second_pattern_when_first_fails(monkeypatch):
    tried: list[str] = []

    def _mock_fetch(url, *_):
        tried.append(url)
        if "achievement-guide" in url:
            return None  # first pattern misses
        return "<p>Trophy guide text</p>"

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    text, url = _fetch_powerpyx("The Evil Within")
    assert len(tried) == 2
    assert "trophy-guide" in url
    assert "Trophy guide text" in text


def test_fetch_powerpyx_returns_empty_when_both_patterns_fail(monkeypatch):
    monkeypatch.setattr(achievement_guide, "fetch_url", MagicMock(return_value=None))
    text, _ = _fetch_powerpyx("The Evil Within")
    assert text == ""


def test_fetch_powerpyx_caps_text_at_limit(monkeypatch):
    long_html = "<p>" + "x" * 100_000 + "</p>"
    monkeypatch.setattr(
        achievement_guide, "fetch_url", MagicMock(return_value=long_html)
    )
    text, _ = _fetch_powerpyx("Game")
    assert len(text) <= achievement_guide._TEXT_LIMIT


# ── _fetch_steam_guides ───────────────────────────────────────────────────────

_GUIDE_LIST_HTML = """
<a href="/sharedfiles/filedetails/?id=111111">Guide One</a>
<a href="/sharedfiles/filedetails/?id=222222">Guide Two</a>
<a href="/sharedfiles/filedetails/?id=111111">Duplicate</a>
"""

_GUIDE_PAGE_HTML = "<p>Step 1: do this. Step 2: do that.</p>"


def test_fetch_steam_guides_returns_guide_content(monkeypatch):
    def _mock_fetch(url, *_):
        if "browsefilter" in url:
            return _GUIDE_LIST_HTML
        return _GUIDE_PAGE_HTML

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    text, source = _fetch_steam_guides(268050)
    assert "Step 1" in text
    assert "steamcommunity.com" in source


def test_fetch_steam_guides_deduplicates_guide_ids(monkeypatch):
    fetched_urls: list[str] = []

    def _mock_fetch(url, *_):
        fetched_urls.append(url)
        if "browsefilter" in url:
            return _GUIDE_LIST_HTML
        return _GUIDE_PAGE_HTML

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    _fetch_steam_guides(268050)
    guide_fetches = [u for u in fetched_urls if "filedetails" in u]
    # 111111 appears twice in _GUIDE_LIST_HTML but should be fetched only once
    assert (
        guide_fetches.count(
            "https://steamcommunity.com/sharedfiles/filedetails/?id=111111"
        )
        == 1
    )


def test_fetch_steam_guides_fetches_at_most_two_guides(monkeypatch):
    many_guides = "\n".join(
        f'<a href="/sharedfiles/filedetails/?id={i}">Guide</a>' for i in range(10)
    )
    fetched_guide_urls: list[str] = []

    def _mock_fetch(url, *_):
        if "browsefilter" in url:
            return many_guides
        fetched_guide_urls.append(url)
        return _GUIDE_PAGE_HTML

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    _fetch_steam_guides(268050)
    assert len(fetched_guide_urls) <= 2


def test_fetch_steam_guides_returns_empty_on_list_failure(monkeypatch):
    monkeypatch.setattr(achievement_guide, "fetch_url", MagicMock(return_value=None))
    text, _ = _fetch_steam_guides(268050)
    assert text == ""


def test_fetch_steam_guides_caps_text_at_limit(monkeypatch):
    long_page = "<p>" + "x" * 100_000 + "</p>"

    def _mock_fetch(url, *_):
        if "browsefilter" in url:
            return _GUIDE_LIST_HTML
        return long_page

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    text, _ = _fetch_steam_guides(268050)
    assert len(text) <= achievement_guide._TEXT_LIMIT


# ── fetch_guide ───────────────────────────────────────────────────────────────


def test_fetch_guide_returns_guide_content(monkeypatch):
    monkeypatch.setattr(
        achievement_guide, "fetch_url", MagicMock(return_value="<p>text</p>")
    )
    result = fetch_guide(268050, "The Evil Within")
    assert isinstance(result, GuideContent)
    assert result.raw_text != ""
    assert result.source != ""


def test_fetch_guide_falls_back_to_powerpyx_when_truesteam_empty(monkeypatch):
    def _mock_fetch(url, *_):
        if "truesteamachievements" in url:
            return None
        if "powerpyx.com" in url:
            return "<p>PowerPyx guide</p>"
        return None  # Steam guides not reached

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    result = fetch_guide(268050, "The Evil Within")
    assert "powerpyx.com" in result.source
    assert result.raw_text != ""


def test_fetch_guide_falls_back_to_steam_when_truesteam_and_powerpyx_empty(monkeypatch):
    def _mock_fetch(url, *_):
        if "truesteamachievements" in url or "powerpyx.com" in url:
            return None
        if "browsefilter" in url:
            return _GUIDE_LIST_HTML
        return _GUIDE_PAGE_HTML

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    result = fetch_guide(268050, "The Evil Within")
    assert "steamcommunity.com" in result.source
    assert result.raw_text != ""


def test_fetch_guide_returns_empty_raw_text_when_all_sources_fail(monkeypatch):
    monkeypatch.setattr(achievement_guide, "fetch_url", MagicMock(return_value=None))
    result = fetch_guide(268050, "The Evil Within")
    assert isinstance(result, GuideContent)
    assert result.raw_text == ""
    assert result.source == "no guide found"


def test_fetch_guide_prefers_truesteam_over_steam(monkeypatch):
    steam_guide_fetched = []

    def _mock_fetch(url, *_):
        if "truesteamachievements" in url:
            return "<p>TSA guide content</p>"
        steam_guide_fetched.append(url)
        return "<p>Steam guide</p>"

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    result = fetch_guide(268050, "The Evil Within")
    assert "truesteamachievements" in result.source
    assert not steam_guide_fetched  # Steam guide was never touched


def test_fetch_guide_debug_prints_on_fallback(monkeypatch, capsys):
    def _mock_fetch(url, *_):
        if "truesteamachievements" in url:
            return None
        if "browsefilter" in url:
            return _GUIDE_LIST_HTML
        return _GUIDE_PAGE_HTML

    monkeypatch.setattr(achievement_guide, "fetch_url", _mock_fetch)
    fetch_guide(268050, "The Evil Within", True)
    captured = capsys.readouterr()
    assert "[debug]" in captured.out
