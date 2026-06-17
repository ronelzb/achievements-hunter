"""
Steam YTD Achievement Leaderboard
==================================
Compares your achievements vs your friends' achievements earned this calendar year.

Setup:
  1. Get a free Steam Web API key: https://steamcommunity.com/dev/apikey
  2. Find your Steam64 ID: https://www.steamidfinder.com/
  3. Run: uv sync
  4. Create a .env file with STEAM_API_KEY and STEAM_ID (see README).

Usage:
  python scripts/steam_ytd_achievements.py
  python scripts/steam_ytd_achievements.py --top 5          # show top 5 friends
  python scripts/steam_ytd_achievements.py --year 2025       # compare a specific year
  python scripts/steam_ytd_achievements.py --concurrency 5  # parallel requests (default: 4)
"""

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import requests
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG (override via env vars or edit directly) ──────────────────────────
API_KEY = os.getenv("STEAM_API_KEY", "YOUR_API_KEY_HERE")
MY_ID = os.getenv("STEAM_ID", "YOUR_STEAM64_ID_HERE")
# Comma-separated vanity names or Steam64 IDs — used when friends list is not public.
# Vanity name = the username in steamcommunity.com/id/USERNAME
# e.g. STEAM_FRIENDS=somevanityname,anotherplayer,76561198009876543
_raw_friends = os.getenv("STEAM_FRIENDS", "")
FRIENDS_OVERRIDE = [f.strip() for f in _raw_friends.split(",") if f.strip()]
# ─────────────────────────────────────────────────────────────────────────────

BASE = "https://api.steampowered.com"

# ── API helpers ───────────────────────────────────────────────────────────────


DEBUG = False
_tls = threading.local()  # per-thread context for debug labels


def get(endpoint: str, params: dict, retries: int = 3) -> dict | None:
    params["key"] = API_KEY
    url = f"{BASE}/{endpoint}"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 429:
                wait = 2**attempt
                print(f"  [rate-limit] waiting {wait}s …")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                _tls.last_status = r.status_code
                if DEBUG:
                    is_achievements = "GetPlayerAchievements" in endpoint
                    silent = is_achievements and r.status_code in (400, 403)
                    if not silent:
                        player = getattr(_tls, "player_name", "")
                        who = f" ({player})" if player else ""
                        if r.status_code >= 500:
                            fate = "retrying…" if attempt < retries - 1 else "giving up"
                            hint = f" (attempt {attempt + 1}/{retries}, {fate})"
                        else:
                            hint = ""
                        print(
                            f"  [debug]{who} {endpoint} → HTTP {r.status_code}{hint}: {r.text[:200]}"
                        )
                if 400 <= r.status_code < 500:
                    return None  # client errors are deterministic, don't retry
                wait = 2**attempt
                time.sleep(wait)
                continue  # 5xx: transient, retry with backoff
            return r.json()
        except requests.RequestException:
            time.sleep(1)
    return None


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
    return [f["steamid"] for f in data.get("friendslist", {}).get("friends", [])]


def get_owned_games(steam_id: str) -> list[dict]:
    data = get(
        "IPlayerService/GetOwnedGames/v1",
        {"steamid": steam_id, "include_appinfo": 1, "include_played_free_games": 1},
    )
    if not data:
        return []
    return data.get("response", {}).get("games", [])


_BLOCKED = -1  # sentinel: achievement fetch blocked (403)
_SERVER_ERROR = -2  # sentinel: achievement fetch failed after all retries (5xx)


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
    for ach in achievements:
        if ach.get("achieved") == 1:
            unlock_ts = ach.get("unlocktime", 0)
            unlock_year = datetime.fromtimestamp(unlock_ts, tz=UTC).year
            if unlock_year == year:
                count += 1
    return count


# ── Core logic ────────────────────────────────────────────────────────────────


def count_ytd_achievements_for_player(
    steam_id: str,
    year: int,
    max_workers: int = 4,
    verbose: bool = False,
) -> int:
    """
    Fetches all owned games for a player and sums up YTD achievements.
    Only processes games where playtime_forever > 0 to skip unplayed games fast.
    """
    games = get_owned_games(steam_id)
    played = [g for g in games if g.get("playtime_forever", 0) > 0]
    # Steam API bug: GetPlayerAchievements returns HTTP 500 (not 400) for games
    # with no achievement schema (e.g. Lethal Company, Don't Starve). The fix is
    # to pre-filter using has_community_visible_stats from GetOwnedGames, which is
    # only present when the game actually has a stats/achievements schema defined.
    with_stats = [g for g in played if g.get("has_community_visible_stats")]

    if verbose:
        skipped = len(played) - len(with_stats)
        skip_note = f", {skipped} skipped (no achievement schema)" if skipped else ""
        print(f"    {len(with_stats)} games with achievements{skip_note}, fetching …")

    game_results: list[tuple[int, dict]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(get_ytd_achievement_count, steam_id, g["appid"], year): g
            for g in with_stats
        }
        for future in as_completed(futures):
            game_results.append((future.result(), futures[future]))

    def _game_name(g: dict) -> str:
        return g.get("name") or f"app {g['appid']}"

    blocked_games = [g for c, g in game_results if c == _BLOCKED]
    failed_games = [g for c, g in game_results if c == _SERVER_ERROR]
    total = sum(c for c, _ in game_results if c > 0)

    if verbose:
        notes = []
        if blocked_games:
            notes.append(f"{len(blocked_games)} game(s) blocked (private stats)")
        if failed_games:
            notes.append(f"{len(failed_games)} game(s) failed (server error)")
        note = " ⚠ " + ", ".join(notes) if notes else ""
        print(f"    → {total} achievements in {year}{note}")
        if blocked_games:
            names = ", ".join(_game_name(g) for g in blocked_games)
            print(f"         blocked:      {names}")
        if failed_games:
            names = ", ".join(_game_name(g) for g in failed_games)
            print(f"         server error: {names}")

    return total


def build_leaderboard(
    year: int,
    top_n: int | None = None,
    max_workers: int = 4,
) -> list[dict]:
    """Returns a sorted list of {name, steam_id, count} dicts."""
    print(f"\n🎮  Steam YTD Achievement Leaderboard — {year}")
    print("=" * 52)

    # Get friends (exclude self in case MY_ID was added to STEAM_FRIENDS)
    friend_ids = [fid for fid in get_friend_ids(MY_ID) if fid != MY_ID]
    print(f"  Friends found: {len(friend_ids)}")

    # Resolve friend names in bulk (GetPlayerSummaries accepts up to 100 IDs)
    player_ids = [MY_ID, *friend_ids]
    names: dict[str, str] = {}
    chunk_size = 100
    for i in range(0, len(player_ids), chunk_size):
        chunk = player_ids[i : i + chunk_size]
        data = get("ISteamUser/GetPlayerSummaries/v2", {"steamids": ",".join(chunk)})
        if data:
            for p in data.get("response", {}).get("players", []):
                names[p["steamid"]] = p.get("personaname", p["steamid"])

    results: list[dict] = []

    def process(steam_id: str) -> dict:
        name = names.get(steam_id, steam_id)
        _tls.player_name = name
        tag = " (YOU)" if steam_id == MY_ID else ""
        print(f"  ⏳ Fetching: {name}{tag}")
        count = count_ytd_achievements_for_player(
            steam_id, year, max_workers=max_workers, verbose=DEBUG
        )
        return {
            "name": name,
            "steam_id": steam_id,
            "count": count,
            "is_me": steam_id == MY_ID,
        }

    # Process yourself first for quick feedback, then friends in parallel
    me_result = process(MY_ID)
    results.append(me_result)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(friend_ids) or 1)) as pool:
        futures = {pool.submit(process, fid): fid for fid in friend_ids}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                print(f"  ⚠  Error for a friend: {exc}")

    results.sort(key=lambda x: x["count"], reverse=True)
    if not top_n:
        return results
    top = results[:top_n]
    if not any(e["is_me"] for e in top):
        me = next((e for e in results if e["is_me"]), None)
        if me:
            top.append(me)
    return top


def print_leaderboard(results: list[dict], year: int) -> None:
    print(f"\n{'Rank':<5} {'Player':<28} {'Achievements':>12}")
    print("─" * 48)
    for rank, entry in enumerate(results, start=1):
        tag = " ◀ YOU" if entry["is_me"] else ""
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"  {rank}.")
        print(f"{medal:<5} {entry['name']:<28} {entry['count']:>12,}{tag}")
    print()

    top = results[0]
    me = next((e for e in results if e["is_me"]), None)
    my_rank = next((i + 1 for i, e in enumerate(results) if e["is_me"]), None)

    if me:
        if my_rank == 1:
            print(f"🏆  You're #1 with {me['count']:,} achievements in {year}. Nice.")
        else:
            gap = top["count"] - me["count"]
            print(
                f"📊  You're #{my_rank} with {me['count']:,} achievements. "
                f"{top['name']} leads by {gap:,}."
            )


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Steam YTD Achievement Leaderboard")
    parser.add_argument(
        "--year",
        type=int,
        default=datetime.now().year,
        help="Calendar year to check (default: current year)",
    )
    parser.add_argument("--top", type=int, default=None, help="Show only top N players")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Parallel requests per player (default: 4)",
    )
    parser.add_argument("--debug", action="store_true", help="Print raw API errors")
    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    if API_KEY == "YOUR_API_KEY_HERE" or MY_ID == "YOUR_STEAM64_ID_HERE":
        print(
            "❌  Please set STEAM_API_KEY and STEAM_ID (env vars or edit CONFIG block)."
        )
        return

    results = build_leaderboard(
        year=args.year,
        top_n=args.top,
        max_workers=args.concurrency,
    )
    print_leaderboard(results, args.year)


if __name__ == "__main__":
    main()
