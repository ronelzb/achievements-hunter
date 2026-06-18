import secrets
import time
from datetime import UTC, datetime

import requests

from .config import FRIENDS_OVERRIDE
from .steam_http import COMMUNITY, FINALIZE_URL, _tls, auth_post, get, get_authed
from .utils import decode_token

_BLOCKED = -1  # sentinel: achievement fetch blocked (403)
_SERVER_ERROR = -2  # sentinel: achievement fetch failed after all retries (5xx)


def get_player_summary(steam_id: str) -> dict:
    data = get("ISteamUser/GetPlayerSummaries/v2", {"steamids": steam_id})
    if data:
        players = data.get("response", {}).get("players", [])
        if players:
            return players[0]
    return {"steamid": steam_id, "personaname": steam_id}


def resolve_vanity_url(vanity: str) -> str | None:
    """Resolves a Steam vanity name (steamcommunity.com/id/NAME) to a Steam64 ID."""
    data = get("ISteamUser/ResolveVanityURL/v1", {"vanityurl": vanity})
    if data:
        response = data.get("response", {})
        if response.get("success") == 1:
            return response["steamid"]
    print(
        f"  ⚠  Could not resolve {vanity!r} — this looks like a display name, not a vanity URL.\n"
        "     Display names are not unique and cannot be looked up.\n"
        "     · Vanity URL  → steamcommunity.com/id/NAME  → use NAME\n"
        "     · No vanity   → steamcommunity.com/profiles/NUMBER → use NUMBER"
    )
    return None


def resolve_friends(entries: list[str]) -> list[str]:
    """Accepts vanity names or raw Steam64 IDs; returns Steam64 IDs."""
    ids = []
    for entry in entries:
        if entry.isdigit():
            ids.append(entry)
        else:
            resolved = resolve_vanity_url(entry)
            if resolved:
                ids.append(resolved)
    return ids


def get_friend_ids(steam_id: str) -> list[str]:
    if FRIENDS_OVERRIDE:
        return resolve_friends(FRIENDS_OVERRIDE)
    data = get(
        "ISteamUser/GetFriendList/v1", {"steamid": steam_id, "relationship": "friend"}
    )
    if not data:
        print(
            "\n⚠️  Friends list unavailable — showing your count only."
            "\n   To include friends, pick one:"
            "\n   A) Steam → View my profile → Edit profile → Privacy Settings → Friends List → Public"
            "\n   B) Add to .env: STEAM_FRIENDS=vanityname1,vanityname2,76561198XXXXXXXXX\n"
        )
        return []
    return [
        friend["steamid"] for friend in data.get("friendslist", {}).get("friends", [])
    ]


def get_owned_games(steam_id: str) -> list[dict]:
    data = get(
        "IPlayerService/GetOwnedGames/v1",
        {"steamid": steam_id, "include_appinfo": 1, "include_played_free_games": 1},
    )
    if not data:
        return []
    return data.get("response", {}).get("games", [])


def generate_api_access_token(
    refresh_token: str, steam_id: str, *, debug: bool = False
) -> tuple[str, str | None]:
    """Exchanges a refresh token for a short-lived Web API access token.

    Returns (access_token, new_refresh_token). new_refresh_token is non-None
    when Steam issues a rotated token — callers must persist it or the next
    call will fail with an empty response.
    """
    payload = decode_token(refresh_token)
    if payload is not None:
        aud = payload.get("aud", [])
        if debug:
            print(f"[debug] refresh token aud: {aud}")
        if "mobile" not in aud:
            raise RuntimeError(
                "Refresh token lacks 'mobile' audience — re-run 'steam-auth --login' to get a new token."
            )
    response = auth_post(
        "GenerateAccessTokenForApp",
        data={
            "refresh_token": refresh_token,
            "steamid": steam_id,
            "renew_refresh_token": 1,
        },
    )
    response.raise_for_status()
    data = response.json().get("response", {})
    access_token = data.get("access_token")
    new_refresh_token = data.get("refresh_token") or None
    if debug:
        print(
            f"[debug] GenerateAccessTokenForApp: access token {'received' if access_token else 'absent'}"
            + (", refresh token rotated" if new_refresh_token else "")
        )
    if not access_token:
        raise RuntimeError(
            f"GenerateAccessTokenForApp returned no access_token: {data}"
        )
    return access_token, new_refresh_token


def get_owned_games_auth(steam_id: str, api_token: str) -> list[dict]:
    """Like get_owned_games, but bypasses the user's privacy settings on their game library.

    The public API returns an empty list when a player's library is set to private.
    This variant authenticates as the player using their own access token, so private
    libraries are visible — ensuring accurate achievement counts for the leaderboard owner.

    `api_token` must come from IAuthenticationService/GenerateAccessTokenForApp/v1.
    That call only succeeds when the stored refresh token carries the 'mobile' audience
    claim, which Steam only issues for logins with platform_type=3 (MobileApp) in
    BeginAuthSessionViaCredentials. The default platform_type=2 (WebBrowser) omits
    'mobile', causing GenerateAccessTokenForApp to return an empty response.

    ISteamUserStats/GetPlayerAchievements does not honour access_token — achievement
    counts are always fetched with the developer API key via get_ytd_achievement_count.
    """
    data = get_authed(
        "IPlayerService/GetOwnedGames/v1",
        {"steamid": steam_id, "include_appinfo": 1, "include_played_free_games": 1},
        access_token=api_token,
    )
    if not data:
        return []
    return data.get("response", {}).get("games", [])


def get_player_summaries_bulk(player_ids: list[str]) -> dict[str, str]:
    """Fetches display names for up to 100 IDs per call. Returns {steamid: name}."""
    names: dict[str, str] = {}
    chunk_size = 100
    for i in range(0, len(player_ids), chunk_size):
        chunk = player_ids[i : i + chunk_size]
        data = get("ISteamUser/GetPlayerSummaries/v2", {"steamids": ",".join(chunk)})
        if data:
            for player in data.get("response", {}).get("players", []):
                names[player["steamid"]] = player.get("personaname", player["steamid"])
    return names


# ── IAuthenticationService ────────────────────────────────────────────────────


def begin_auth(username: str, encrypted_password: str, rsa_timestamp: str) -> dict:
    """Starts an IAuthenticationService auth session. Returns the response dict."""
    response = auth_post(
        "BeginAuthSessionViaCredentials",
        data={
            "account_name": username,
            "encrypted_password": encrypted_password,
            "encryption_timestamp": rsa_timestamp,
            "remember_login": "true",
            "platform_type": 3,
            "persistence": 1,
        },
    )
    response.raise_for_status()
    data = response.json().get("response", {})
    if not data.get("client_id"):
        raise RuntimeError(
            data.get("error_message")
            or "Login failed — check your username and password."
        )
    return data


def submit_guard_code(client_id: str, steam_id: str, code: str, code_type: int) -> None:
    """Submits a Steam Guard code to approve the pending auth session."""
    response = auth_post(
        "UpdateAuthSessionWithSteamGuardCode",
        data={
            "client_id": client_id,
            "steamid": steam_id,
            "code": code,
            "code_type": code_type,
        },
    )
    response.raise_for_status()


def poll_auth_session(client_id: str, request_id: str, interval: float = 5.0) -> str:
    """Polls until the auth session is approved; returns the refresh token."""
    for _ in range(12):
        response = auth_post(
            "PollAuthSessionStatus",
            data={"client_id": client_id, "request_id": request_id},
        )
        response.raise_for_status()
        data = response.json().get("response", {})
        refresh_token = data.get("refresh_token")
        if refresh_token:
            return refresh_token
        time.sleep(interval)
    raise RuntimeError("Login timed out waiting for Steam Guard approval.")


def finalize_session(refresh_token: str, steam_id: str, *, debug: bool = False) -> str:
    """Exchanges a refresh token for the steamcommunity.com steamLoginSecure cookie."""
    session_id = secrets.token_hex(12)
    with requests.Session() as http:
        http.cookies.set("sessionid", session_id)
        finalize_response = http.post(
            FINALIZE_URL,
            data={
                "nonce": refresh_token,
                "sessionid": session_id,
                "redir": f"{COMMUNITY}/login/home/?goto=",
            },
            headers={"Origin": COMMUNITY, "Referer": f"{COMMUNITY}/"},
            timeout=15,
        )
        finalize_response.raise_for_status()
        if debug:
            print(f"[debug] finalize cookies set: {list(http.cookies.keys())}")
        transfer_info = finalize_response.json().get("transfer_info", [])
        if debug:
            urls = [t.get("url", "") for t in transfer_info]
            print(
                f"[debug] finalize returned {len(transfer_info)} transfer URL(s): {urls}"
            )
        community_transfer = next(
            (t for t in transfer_info if "steamcommunity.com" in t.get("url", "")),
            None,
        )
        if not community_transfer:
            raise RuntimeError(
                "Login failed: no steamcommunity.com transfer in finalize response."
            )
        if debug:
            print(
                f"[debug] transfer params keys: {list(community_transfer['params'].keys())}"
            )
        transfer_response = http.post(
            community_transfer["url"],
            data={
                "steamID": steam_id,
                **community_transfer["params"],
                "sessionid": session_id,
            },
            allow_redirects=False,
            timeout=15,
        )
        transfer_response.raise_for_status()
        if debug:
            print(f"[debug] transfer response: HTTP {transfer_response.status_code}")
            print(f"[debug] response cookies: {list(transfer_response.cookies.keys())}")
            print(f"[debug] session cookies: {list(http.cookies.keys())}")
            print(f"[debug] response body: {transfer_response.text[:400]}")
        cookie = transfer_response.cookies.get("steamLoginSecure") or http.cookies.get(
            "steamLoginSecure"
        )
        if not cookie:
            raise RuntimeError(
                "Login failed: steamLoginSecure cookie not set after transfer."
            )
        return cookie


def get_ytd_achievement_count(steam_id: str, app_id: int, year: int) -> int:
    """Returns achievements unlocked during `year`, or a sentinel if the fetch failed."""
    _tls.last_status = None
    data = get(
        "ISteamUserStats/GetPlayerAchievements/v1",
        {"steamid": steam_id, "appid": app_id, "l": "english"},
    )
    if not data:
        status = getattr(_tls, "last_status", None)
        if status == 403:
            return _BLOCKED
        if status is not None and status >= 500:
            return _SERVER_ERROR
        return 0
    achievements = data.get("playerstats", {}).get("achievements", [])
    count = 0
    for achievement in achievements:
        if achievement.get("achieved") == 1:
            unlock_ts = achievement.get("unlocktime", 0)
            unlock_year = datetime.fromtimestamp(unlock_ts, tz=UTC).year
            if unlock_year == year:
                count += 1
    return count
