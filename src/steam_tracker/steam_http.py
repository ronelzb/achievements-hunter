import threading
import time

import requests

from .settings import API_KEY

DEBUG = False
_tls = threading.local()  # per-thread context for debug labels
BASE = "https://api.steampowered.com"
COMMUNITY = "https://steamcommunity.com"
STORE = "https://store.steampowered.com"
AUTH_API = f"{BASE}/IAuthenticationService"
FINALIZE_URL = "https://login.steampowered.com/jwt/finalizelogin"


def auth_post(endpoint: str, data: dict, *, timeout: int = 15) -> requests.Response:
    """POST to IAuthenticationService. `endpoint` is the method name without the /v1 suffix."""
    return requests.post(f"{AUTH_API}/{endpoint}/v1", data=data, timeout=timeout)


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


def _api_get(endpoint: str, params: dict, retries: int) -> dict | None:
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
                    return None
                wait = 2**attempt
                time.sleep(wait)
                continue
            return response.json()
        except requests.RequestException:
            time.sleep(1)
    return None


def store_get(
    path: str, params: dict | None = None, *, timeout: int = 10
) -> dict | None:
    """GET a store.steampowered.com path. Returns None on any network or HTTP error."""
    try:
        response = requests.get(f"{STORE}/{path}", params=params or {}, timeout=timeout)
        if response.status_code != 200:
            return None
        return response.json()
    except requests.RequestException:
        return None


def get(endpoint: str, params: dict, retries: int = 3) -> dict | None:
    return _api_get(endpoint, {**params, "key": API_KEY}, retries)


def get_authed(
    endpoint: str, params: dict, *, access_token: str, retries: int = 3
) -> dict | None:
    """Like get() but authenticates with a user OAuth access token instead of the developer API key."""
    return _api_get(endpoint, {**params, "access_token": access_token}, retries)
