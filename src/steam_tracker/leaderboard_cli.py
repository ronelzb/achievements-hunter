import argparse
from datetime import datetime

from . import steam_http
from .config import API_KEY, MY_ID
from .leaderboard import build_leaderboard


def print_leaderboard(results: list[dict], year: int) -> None:
    print(f"\n{'Rank':<5} {'Player':<28} {'Achievements':>12}")
    print("─" * 48)
    for rank, entry in enumerate(results, start=1):
        tag = " ◀ YOU" if entry["is_me"] else ""
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"  {rank}.")
        print(f"{medal:<5} {entry['name']:<28} {entry['count']:>12,}{tag}")
    print()

    top = results[0]
    me = next((entry for entry in results if entry["is_me"]), None)
    my_rank = next(
        (rank for rank, entry in enumerate(results, start=1) if entry["is_me"]), None
    )

    if me:
        if my_rank == 1:
            print(f"🏆  You're #1 with {me['count']:,} achievements in {year}. Nice.")
        else:
            gap = top["count"] - me["count"]
            print(
                f"📊  You're #{my_rank} with {me['count']:,} achievements. "
                f"{top['name']} leads by {gap:,}."
            )


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

    steam_http.DEBUG = args.debug

    if API_KEY == "YOUR_API_KEY_HERE" or MY_ID == "YOUR_STEAM64_ID_HERE":
        print(
            "❌  Please set STEAM_API_KEY and STEAM_ID (env vars or edit CONFIG block)."
        )
        return

    results = build_leaderboard(
        year=args.year,
        top_n=args.top,
        max_workers=args.concurrency,
        debug=args.debug,
    )
    print_leaderboard(results, args.year)
