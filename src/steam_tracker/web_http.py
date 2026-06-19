"""Generic external URL fetching for web scraping.

Distinct from steam_http.py, which handles Steam API / Community calls
(API key auth, per-endpoint retries, rate-limit backoff).  This module is
for arbitrary third-party pages where we impersonate a browser and treat
any failure as a best-effort miss rather than an error.
"""

from __future__ import annotations

import requests

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_TIMEOUT = 15


def fetch_url(url: str, debug: bool = False) -> str | None:
    """GET *url* and return the response body as text, or None on any failure.

    Non-200 responses and network errors both return None so callers can
    treat this as a best-effort fetch without special-casing error types.
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            if debug:
                print(f"[debug] fetch {url} -> HTTP {response.status_code}")
            return None
        return response.text
    except requests.RequestException as exc:
        if debug:
            print(f"[debug] fetch failed: {url} — {exc}")
        return None
