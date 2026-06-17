from datetime import UTC, datetime

from .config import FRIENDS_OVERRIDE
from .steam_http import _tls, get

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
