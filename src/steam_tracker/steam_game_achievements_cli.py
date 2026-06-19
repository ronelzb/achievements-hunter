import argparse
from datetime import UTC, datetime

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import steam_http
from .settings import API_KEY
from .steam_api import (
    get_all_player_achievements,
    get_game_schema,
    get_local_achievement_descs,
    search_apps,
)
from .steam_auth import get_my_id

console = Console(highlight=False, markup=False)


def _pick_app(query: str) -> tuple[int, str] | None:
    results = search_apps(query)
    if not results:
        console.print(f"❌  No games found matching '{query}'.")
        return None
    if len(results) == 1:
        return results[0]["id"], results[0]["name"]
    console.print(f"\nFound {len(results)} matches for '{query}':")
    for i, app in enumerate(results, start=1):
        console.print(f"  {i:2}. {app['name']}  (App ID: {app['id']})")
    try:
        raw = input("\nPick a number (or Enter to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    if not raw:
        return None
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(results):
            return results[idx]["id"], results[idx]["name"]
    except ValueError:
        pass
    console.print("❌  Invalid selection.")
    return None


def _print_table(
    schema: list[dict],
    player: list[dict],
    *,
    filter_mode: str,
    sort_mode: str,
    game_name: str,
    app_id: int,
    reveal_hidden: bool = False,
    local_descs: dict[str, str] | None = None,
) -> None:
    player_map = {a["apiname"]: a for a in player}
    local_map = local_descs or {}

    merged = []
    for schema_idx, ach in enumerate(schema, start=1):
        key = ach["name"]
        p = player_map.get(key, {})
        achieved = bool(p.get("achieved", 0))
        unlock_ts = p.get("unlocktime", 0) if achieved else 0
        display_name = ach.get("displayName") or ach["name"]
        schema_desc = ach.get("description") or ""
        player_desc = p.get("description") or ""
        local_desc = local_map.get(key, "")
        is_hidden = bool(ach.get("hidden"))
        if achieved:
            from_local = not (player_desc or schema_desc) and bool(local_desc)
            description = player_desc or schema_desc or local_desc
        elif is_hidden and not reveal_hidden:
            from_local = False
            description = "(Hidden)"
        else:
            from_local = not schema_desc and bool(local_desc)
            description = schema_desc or local_desc
        merged.append(
            {
                "schema_idx": schema_idx,
                "name": display_name,
                "description": description,
                "from_local": from_local,
                "achieved": achieved,
                "unlocktime": unlock_ts,
            }
        )

    if sort_mode == "won-first":
        # stable: won sorted by unlock time desc, not-won keeps schema order
        merged.sort(
            key=lambda ach: (0, -ach["unlocktime"]) if ach["achieved"] else (1, 0)
        )

    if filter_mode == "won":
        merged = [ach for ach in merged if ach["achieved"]]
    elif filter_mode == "not-won":
        merged = [ach for ach in merged if not ach["achieved"]]

    total = len(schema)
    won = sum(1 for ach in schema if player_map.get(ach["name"], {}).get("achieved", 0))
    pct = won / total * 100 if total else 0.0

    console.print(f"\nGame: {game_name} (App ID: {app_id})")
    console.print(f"Achievements: {won} / {total} won ({pct:.1f}%)")

    if not merged:
        console.print("  (no achievements match the filter)")
        return

    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
    table.add_column("#", justify="right", no_wrap=True, style="dim")
    table.add_column("", no_wrap=True)
    table.add_column("Achievement", no_wrap=True)
    table.add_column("Description")
    table.add_column("Unlocked", no_wrap=True)

    for row, ach in enumerate(merged, start=1):
        num = str(ach["schema_idx"]) if sort_mode == "steam" else str(row)
        status = "✓" if ach["achieved"] else "✗"
        if ach["achieved"] and ach["unlocktime"]:
            unlocked = datetime.fromtimestamp(ach["unlocktime"], tz=UTC).strftime(
                "%Y-%m-%d"
            )
        else:
            unlocked = "—"
        if ach["from_local"]:
            desc_cell = Text.assemble(("[SteamCache] ", "dim"), ach["description"])
        else:
            desc_cell = Text(ach["description"])
        table.add_row(num, status, ach["name"], desc_cell, unlocked)

    console.print()
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="List achievements for a Steam game")
    parser.add_argument("query", nargs="?", help="Game name to search")
    parser.add_argument(
        "--app-id", type=int, metavar="ID", help="Steam App ID (skip search)"
    )
    parser.add_argument(
        "--filter",
        "-f",
        choices=["won", "not-won", "all"],
        default="all",
        help="Show won, not-won, or all achievements (default: all)",
    )
    parser.add_argument(
        "--sort",
        "-s",
        choices=["won-first", "steam"],
        default="won-first",
        help="Sort order: won-first (default) or steam (schema order)",
    )
    parser.add_argument(
        "--reveal-hidden",
        action="store_true",
        help="Show descriptions for hidden achievements not yet won (spoilers)",
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Print raw API errors"
    )
    args = parser.parse_args()

    if not args.app_id and not args.query:
        parser.error("provide a game name to search or use --app-id")

    steam_http.DEBUG = args.debug

    my_id = get_my_id(args.debug)
    if API_KEY == "YOUR_API_KEY_HERE" or not my_id:
        console.print(
            "❌  Please set STEAM_API_KEY in .env and either set STEAM_ID or run steam-login."
        )
        return

    if args.app_id:
        app_id = args.app_id
        app_name = ""
    elif args.query:
        result = _pick_app(args.query)
        if result is None:
            return
        app_id, app_name = result
    else:
        return  # unreachable: parser.error() above already exits

    schema_name, schema = get_game_schema(app_id)
    if not schema:
        console.print(
            f"❌  No achievements found for App ID {app_id}."
            " The game may not have achievements or the schema is unavailable."
        )
        return

    if not app_name:
        app_name = schema_name or f"App {app_id}"

    player = get_all_player_achievements(my_id, app_id)
    if player is None:
        console.print(
            "❌  Could not fetch your achievements. Possible causes:\n"
            "   · The game's stats are private — run steam-login to authenticate\n"
            "   · You haven't played this game\n"
            "   · The game was removed from your library"
        )
        return

    local_descs = get_local_achievement_descs(app_id, args.debug)
    _print_table(
        schema,
        player,
        filter_mode=args.filter,
        sort_mode=args.sort,
        game_name=app_name,
        app_id=app_id,
        reveal_hidden=args.reveal_hidden,
        local_descs=local_descs,
    )
