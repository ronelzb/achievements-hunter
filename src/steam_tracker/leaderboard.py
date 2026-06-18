from concurrent.futures import ThreadPoolExecutor, as_completed

from .steam_api import (
    _BLOCKED,
    _SERVER_ERROR,
    filter_by_display_name,
    get_friend_ids,
    get_owned_games,
    get_owned_games_auth,
    get_player_summaries_bulk,
    get_ytd_achievement_count,
)
from .steam_http import _tls


def count_ytd_achievements_for_player(
    steam_id: str,
    year: int,
    max_workers: int = 4,
    verbose: bool = False,
    api_token: str | None = None,
    label: str = "",
) -> int:
    """
    Fetches all owned games for a player and sums up YTD achievements.
    Only processes games where playtime_forever > 0 to skip unplayed games fast.
    """
    games = (
        get_owned_games_auth(steam_id, api_token)
        if api_token
        else get_owned_games(steam_id)
    )
    played = [game for game in games if game.get("playtime_forever", 0) > 0]
    # Steam API bug: GetPlayerAchievements returns HTTP 500 (not 400) for games
    # with no achievement schema (e.g. Lethal Company, Don't Starve). The fix is
    # to pre-filter using has_community_visible_stats from GetOwnedGames, which is
    # only present when the game actually has a stats/achievements schema defined.
    with_stats = [game for game in played if game.get("has_community_visible_stats")]

    if verbose:
        skipped = len(played) - len(with_stats)
        skip_note = f", {skipped} skipped (no achievement schema)" if skipped else ""
        source = "auth" if api_token else "public API"
        private_hint = " — Game Details may be private" if games and not played else ""
        prefix = f"    [{label}] " if label else "    "
        print(
            f"{prefix}{len(games)} games via {source} ({len(played)} played{private_hint}), "
            f"{len(with_stats)} with achievements{skip_note}, fetching …"
        )

    def fetch_count(app_id: int) -> int:
        return get_ytd_achievement_count(steam_id, app_id, year)

    game_results: list[tuple[int, dict]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_count, game["appid"]): game for game in with_stats}
        for future in as_completed(futures):
            game_results.append((future.result(), futures[future]))

    def _game_name(game: dict) -> str:
        return game.get("name") or f"app {game['appid']}"

    blocked_games = [
        game
        for achievement_count, game in game_results
        if achievement_count == _BLOCKED
    ]
    failed_games = [
        game
        for achievement_count, game in game_results
        if achievement_count == _SERVER_ERROR
    ]
    total = sum(
        achievement_count
        for achievement_count, _ in game_results
        if achievement_count > 0
    )

    if verbose:
        notes = []
        if blocked_games:
            notes.append(f"{len(blocked_games)} game(s) blocked (private stats)")
        if failed_games:
            notes.append(f"{len(failed_games)} game(s) failed (server error)")
        note = " ⚠ " + ", ".join(notes) if notes else ""
        prefix = f"    [{label}] " if label else "    "
        print(f"{prefix}→ {total} achievements in {year}{note}")
        if blocked_games:
            game_names = ", ".join(_game_name(game) for game in blocked_games)
            print(f"{prefix}    blocked:      {game_names}")
        if failed_games:
            game_names = ", ".join(_game_name(game) for game in failed_games)
            print(f"{prefix}    server error: {game_names}")

    return total


def build_leaderboard(
    year: int,
    my_id: str,
    top_n: int | None = None,
    max_workers: int = 4,
    debug: bool = False,
    api_token: str | None = None,
    filter_names: list[str] | None = None,
) -> list[dict]:
    """Returns a sorted list of {name, steam_id, count, is_me} dicts."""
    print(f"\n🎮  Steam YTD Achievement Leaderboard — {year}")
    print("=" * 52)

    friend_ids = [
        friend_id for friend_id in get_friend_ids(my_id) if friend_id != my_id
    ]
    print(f"  Friends found: {len(friend_ids)}")

    player_ids = [my_id, *friend_ids]
    names = get_player_summaries_bulk(player_ids)

    if filter_names:
        entries = [(fid, names.get(fid, fid)) for fid in friend_ids]
        friend_ids, unmatched = filter_by_display_name(entries, filter_names)
        if debug and unmatched:
            for term in unmatched:
                print(f"[debug] no friends matched filter term: {term!r}")
            searched = ", ".join(name for _, name in entries)
            print(f"[debug] friends searched ({len(entries)}): {searched}")
        print(f"  Filtered to: {len(friend_ids)} friend(s)")
        player_ids = [my_id, *friend_ids]

    results: list[dict] = []

    def process(steam_id: str) -> dict:
        name = names.get(steam_id, steam_id)
        _tls.player_name = name
        tag = " (YOU)" if steam_id == my_id else ""
        print(f"  ⏳ Fetching: {name}{tag}")
        count = count_ytd_achievements_for_player(
            steam_id,
            year,
            max_workers=max_workers,
            verbose=debug,
            api_token=api_token if steam_id == my_id else None,
            label=name,
        )
        return {
            "name": name,
            "steam_id": steam_id,
            "count": count,
            "is_me": steam_id == my_id,
        }

    me_result = process(my_id)
    results.append(me_result)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(friend_ids) or 1)) as pool:
        futures = {
            pool.submit(process, friend_id): friend_id for friend_id in friend_ids
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                print(f"  ⚠  Error for a friend: {exc}")

    results.sort(key=lambda entry: entry["count"], reverse=True)
    if not top_n:
        return results
    top = results[:top_n]
    if not any(entry["is_me"] for entry in top):
        me = next((entry for entry in results if entry["is_me"]), None)
        if me:
            top.append(me)
    return top
