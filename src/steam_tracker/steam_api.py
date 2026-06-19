import secrets
import time
from datetime import UTC, datetime

import requests

from .config import FRIENDS_OVERRIDE
from .steam_http import (
    COMMUNITY,
    FINALIZE_URL,
    _tls,
    auth_post,
    get,
    get_authed,
    store_get,
)
from .utils import decode_token

_BLOCKED = -1  # sentinel: achievement fetch blocked (403)
_SERVER_ERROR = -2  # sentinel: achievement fetch failed after all retries (5xx)
_CHUNK_SIZE = 100


def get_player_summary(steam_id: str) -> dict:
    """Returns the player summary dict, or a stub {steamid, personaname} on API failure.

    The stub ensures callers can always read personaname without a None check.
    """
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
    """Returns Steam64 IDs of the player's friends.

    Checks FRIENDS_OVERRIDE first (env var STEAM_FRIENDS), which lets users
    hardcode a friend list without making their Steam friends list public.
    Falls back to GetFriendList; returns [] with a printed hint when the API
    returns nothing (typically because the friends list is set to private).
    """
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
    """Returns the player's owned games with app info and free-to-play titles included.

    include_appinfo adds name and has_community_visible_stats (used to skip games
    with no achievement schema). include_played_free_games ensures F2P titles like
    TF2 appear — they are omitted by default.
    """
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
    if payload is None:
        if debug:
            print(
                "[debug] refresh token could not be decoded — run: steam-auth --logout then --login"
            )
    else:
        aud = payload.get("aud", [])
        if debug:
            print(f"[debug] refresh token aud: {aud}")
        if "mobile" not in aud:
            raise RuntimeError(
                "Refresh token lacks 'mobile' audience — run: steam-auth --logout then --login"
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

    Verified against official Steam docs (partner.steamgames.com/doc/webapi/isteamuserstats):
    the `key` parameter is mandatory with no token-based alternative. The OAuth-enabled
    WebAPI services are a fixed list (ICloudService, IBroadcastService,
    IGameNotificationsService, IPlayerService, IPublishedFileService) — ISteamUserStats
    is not among them. STEAM_API_KEY cannot be derived from the login session.
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
    for i in range(0, len(player_ids), _CHUNK_SIZE):
        chunk = player_ids[i : i + _CHUNK_SIZE]
        data = get("ISteamUser/GetPlayerSummaries/v2", {"steamids": ",".join(chunk)})
        if data:
            for player in data.get("response", {}).get("players", []):
                names[player["steamid"]] = player.get("personaname", player["steamid"])
    return names


def get_player_summaries_bulk_full(player_ids: list[str]) -> list[dict]:
    """Fetches full player summary dicts for up to 100 IDs per call."""
    players: list[dict] = []
    for i in range(0, len(player_ids), _CHUNK_SIZE):
        chunk = player_ids[i : i + _CHUNK_SIZE]
        data = get("ISteamUser/GetPlayerSummaries/v2", {"steamids": ",".join(chunk)})
        if data:
            players.extend(data.get("response", {}).get("players", []))
    return players


def filter_by_display_name(
    entries: list[tuple[str, str]], terms: list[str]
) -> tuple[list[str], list[str]]:
    """Filters (steam_id, display_name) pairs by case-insensitive substring terms.

    Returns (matched_ids, unmatched_terms). Each ID is included at most once;
    a term is unmatched when no entry's name contains it as a substring.
    """
    lower_terms = [term.lower() for term in terms]
    matched_ids: list[str] = []
    matched_indices: set[int] = set()
    for steam_id, name in entries:
        name_lower = name.lower()
        for i, term in enumerate(lower_terms):
            if term in name_lower:
                matched_ids.append(steam_id)
                matched_indices.add(i)
                break
    unmatched_terms = [term for i, term in enumerate(terms) if i not in matched_indices]
    return matched_ids, unmatched_terms


# ── IAuthenticationService ────────────────────────────────────────────────────


def begin_auth(username: str, encrypted_password: str, rsa_timestamp: str) -> dict:
    """Starts a BeginAuthSessionViaCredentials session and returns the response dict.

    The response contains client_id, request_id, steamid, interval, and
    allowed_confirmations, which are forwarded to the guard and polling steps.

    Field rationale:
    - encryption_timestamp: must match the RSA key version Steam issued; Steam
      rejects requests where the timestamp doesn't correspond to the active key.
    - platform_type 3 (MobileApp): causes Steam to embed "mobile" in the refresh
      token's JWT aud claim. That claim is required by GenerateAccessTokenForApp —
      platform_type 2 (WebBrowser) omits it and makes that call return an empty
      response. See generate_api_access_token for details.
    - persistence 1 + remember_login: request a long-lived refresh token instead
      of a session-scoped one, so the stored token survives across reboots without
      needing to re-authenticate.
    """
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
    """Submits a Steam Guard code to approve the pending auth session.

    code_type mirrors EAuthSessionGuardType:
        * 2 = email code
        * 3 = TOTP authenticator code
        * 4 = mobile app confirmation (no code — user taps Approve in the app).
    """
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
    """Polls PollAuthSessionStatus until approved and returns the refresh token.

    `interval` should be the value from BeginAuthSessionViaCredentials (Steam's
    recommended polling rate, typically 5 s). Raises RuntimeError after 12 attempts
    (~60 s at the default interval) — enough time for the user to respond to a
    Steam Guard prompt without blocking indefinitely.
    """
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
    """Exchanges a refresh token for the steamcommunity.com steamLoginSecure cookie.

    Steam's finalize flow is two-phase: POST to /jwt/finalizelogin returns a
    transfer_info list of per-domain URLs. We pick the steamcommunity.com entry
    and POST to it with allow_redirects=False — following the redirect would lose
    the Set-Cookie header that carries steamLoginSecure.
    """
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


def search_apps(query: str) -> list[dict]:
    """Searches the Steam store for apps matching query. Returns [{id, name}] dicts."""
    data = store_get("api/storesearch/", {"term": query, "l": "english", "cc": "US"})
    if not data:
        return []
    return [
        {"id": item["id"], "name": item["name"]}
        for item in data.get("items", [])
        if item.get("type") == "app"
    ]


def get_game_schema(app_id: int) -> tuple[str, list[dict]]:
    """Returns (game_name, achievements) from GetSchemaForGame.

    Returns ("", []) if the game has no achievement schema.
    Each achievement dict has: name, displayName, description, hidden, icon, icongray.
    """
    data = get("ISteamUserStats/GetSchemaForGame/v2", {"appid": app_id, "l": "english"})
    if not data:
        return "", []
    game = data.get("game", {})
    name = game.get("gameName", "")
    achievements = game.get("availableGameStats", {}).get("achievements", [])
    return name, achievements


def get_all_player_achievements(steam_id: str, app_id: int) -> list[dict] | None:
    """Returns all achievements for a player in a game, or None on failure.

    Each dict has: apiname, achieved (0|1), unlocktime, name, description.
    Returns None when the request is blocked (403 / success=false) — typically
    because the game's stats are private or the player has never played it.
    """
    _tls.last_status = None
    data = get(
        "ISteamUserStats/GetPlayerAchievements/v1",
        {"steamid": steam_id, "appid": app_id, "l": "english"},
    )
    if not data:
        return None
    playerstats = data.get("playerstats", {})
    if not playerstats.get("success"):
        return None
    return playerstats.get("achievements", [])


def get_ytd_achievement_count(steam_id: str, app_id: int, year: int) -> int:
    """Returns achievements unlocked during `year`, or a sentinel on failure.

    Returns _BLOCKED (-1) on HTTP 403 — the game's stats are private.
    Returns _SERVER_ERROR (-2) on HTTP 5xx — Steam returns 500 (not 400) for
    games that never had an achievement schema, so callers pre-filter with
    has_community_visible_stats to avoid hitting this path for most games.
    Callers must exclude both sentinels from totals.
    """
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
