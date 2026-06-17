import threading
import time

import requests

from .config import API_KEY

DEBUG = False
_tls = threading.local()  # per-thread context for debug labels
BASE = "https://api.steampowered.com"
COMMUNITY = "https://steamcommunity.com"


def community_get(
    path: str,
    *,
    cookies: dict | None = None,
    allow_redirects: bool = True,
    timeout: int = 10,
) -> requests.Response | None:
    """GET a steamcommunity.com path. Returns None on any network error."""
    try:
        return requests.get(
            f"{COMMUNITY}/{path}",
            cookies=cookies,
            allow_redirects=allow_redirects,
            timeout=timeout,
        )
    except requests.RequestException:
        return None


def community_post(
    path: str,
    *,
    data: dict | None = None,
    timeout: int = 15,
) -> requests.Response:
    """POST to a steamcommunity.com path with form data."""
    return requests.post(f"{COMMUNITY}/{path}", data=data, timeout=timeout)


def get(endpoint: str, params: dict, retries: int = 3) -> dict | None:
    params["key"] = API_KEY
    url = f"{BASE}/{endpoint}"
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 429:
                wait = 2**attempt
                print(f"  [rate-limit] waiting {wait}s …")
                time.sleep(wait)
                continue
            if response.status_code != 200:
                _tls.last_status = response.status_code
                if DEBUG:
                    is_achievements = "GetPlayerAchievements" in endpoint
                    silent = is_achievements and response.status_code in (400, 403)
                    if not silent:
                        player = getattr(_tls, "player_name", "")
                        who = f" ({player})" if player else ""
                        if response.status_code >= 500:
                            fate = "retrying…" if attempt < retries - 1 else "giving up"
                            hint = f" (attempt {attempt + 1}/{retries}, {fate})"
                        else:
                            hint = ""
                        print(
                            f"  [debug]{who} {endpoint} → HTTP {response.status_code}{hint}: {response.text[:200]}"
                        )
                if 400 <= response.status_code < 500:
                    return None  # client errors are deterministic, don't retry
                wait = 2**attempt
                time.sleep(wait)
                continue  # 5xx: transient, retry with backoff
            return response.json()
        except requests.RequestException:
            time.sleep(1)
    return None
