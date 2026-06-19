"""Fetch plain-text achievement guide content from external sources.

Source priority (tried in order, first non-empty result wins):
1. TrueSteamAchievements — Steam-specific, structured per-achievement pages.
2. PowerPyx — high-quality editorial guides; tries two common URL patterns
   (achievement-guide-and-roadmap, trophy-guide-roadmap) because PowerPyx
   doesn't expose a stable slug formula.
3. Steam Community top-rated guides — user-generated, variable quality, but
   available for virtually every game on Steam.

Alternatives considered and skipped:
- TrueAchievements (trueachievements.com): Xbox-focused achievement tracker;
  overlaps with Steam for multiplatform titles but is not Steam-specific.
- Reddit (reddit.com/r/<game>, r/achievementhunter): guides exist but there is
  no reliable URL formula — would require a search API step.

To add a new source, append a (label, lambda) entry to the `sources` list
inside fetch_guide.
"""

from __future__ import annotations

import re

from .contracts import GuideContent
from .parser import HtmlParser
from .utils import game_slug
from .web_http import fetch_url

_TEXT_LIMIT = 60_000
_html_parser = HtmlParser()


# ---------------------------------------------------------------------------
# Source fetchers  (each takes only what it needs)
# ---------------------------------------------------------------------------


def _fetch_truesteam(game_name: str, debug: bool = False) -> tuple[str, str]:
    """TrueSteamAchievements achievements page for the game."""
    slug = game_slug(game_name)
    url = f"https://www.truesteamachievements.com/game/{slug}/achievements"
    if debug:
        print(f"[debug] TrueSteamAchievements URL: {url}")
    raw = fetch_url(url, debug)
    if not raw:
        return "", url
    return _html_parser.parse(raw)[:_TEXT_LIMIT], url


def _fetch_powerpyx(game_name: str, debug: bool = False) -> tuple[str, str]:
    """PowerPyx guide page, trying two common URL slug patterns."""
    slug = game_slug(game_name)
    patterns = [
        f"https://www.powerpyx.com/{slug}-achievement-guide-and-roadmap/",
        f"https://www.powerpyx.com/{slug}-trophy-guide-roadmap/",
    ]
    for url in patterns:
        if debug:
            print(f"[debug] PowerPyx URL: {url}")
        raw = fetch_url(url, debug)
        if raw:
            return _html_parser.parse(raw)[:_TEXT_LIMIT], url
    return "", patterns[0]


def _fetch_steam_guides(app_id: int, debug: bool = False) -> tuple[str, str]:
    """Top-rated Steam Community guides for the app (up to 2 guides)."""
    list_url = f"https://steamcommunity.com/app/{app_id}/guides/?browsefilter=toprated"
    if debug:
        print(f"[debug] Steam guides list URL: {list_url}")
    list_html = fetch_url(list_url, debug)
    if not list_html:
        return "", list_url

    guide_ids = re.findall(r"sharedfiles/filedetails/\?id=(\d+)", list_html)
    unique_ids = list(dict.fromkeys(guide_ids))

    texts: list[str] = []
    for gid in unique_ids[:2]:
        guide_url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={gid}"
        if debug:
            print(f"[debug] fetching Steam guide: {guide_url}")
        raw = fetch_url(guide_url, debug)
        if raw:
            texts.append(_html_parser.parse(raw))

    combined = "\n\n".join(texts)
    return combined[:_TEXT_LIMIT], list_url


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_guide(app_id: int, game_name: str, debug: bool = False) -> GuideContent:
    """Return GuideContent with scraped guide text. raw_text is '' if all sources fail."""
    sources = [
        ("TrueSteamAchievements", lambda: _fetch_truesteam(game_name, debug)),
        ("PowerPyx", lambda: _fetch_powerpyx(game_name, debug)),
        ("Steam guides", lambda: _fetch_steam_guides(app_id, debug)),
    ]
    for label, fetch in sources:
        text, source = fetch()
        if text.strip():
            return GuideContent(source=source, raw_text=text)
        if debug:
            print(f"[debug] {label} returned empty, trying next source")

    if debug:
        print("[debug] all guide sources failed")
    return GuideContent(source="no guide found", raw_text="")
