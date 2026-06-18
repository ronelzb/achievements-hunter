import argparse
from datetime import datetime

from . import steam_http
from .config import API_KEY
from .leaderboard import build_leaderboard
from .steam_api import generate_api_access_token
from .steam_auth import (
    get_my_id,
    load_refresh_token,
    load_session,
    save_refresh_token,
    validate_session,
)


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
        "--filter",
        "-f",
        nargs="+",
        metavar="NAME",
        help="Compare only with friends whose display name contains NAME (case-insensitive)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Parallel requests per player (default: 4)",
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Print raw API errors"
    )
    args = parser.parse_args()

    steam_http.DEBUG = args.debug

    my_id = get_my_id(debug=args.debug)
    if API_KEY == "YOUR_API_KEY_HERE" or not my_id:
        print(
            "❌  Please set STEAM_API_KEY in .env and, either STEAM_ID or run steam-login first."
        )
        return

    raw = load_session()
    api_token: str | None = None
    if not raw:
        if args.debug:
            print("[debug] no session cookie in keyring — run steam-login first")
    elif not validate_session(raw, debug=args.debug):
        if args.debug:
            print(
                "[debug] session invalid — using public endpoints (re-run steam-login)"
            )
    else:
        refresh_token = load_refresh_token()
        if refresh_token:
            try:
                api_token, new_refresh = generate_api_access_token(
                    refresh_token, my_id, debug=args.debug
                )
                if new_refresh:
                    save_refresh_token(new_refresh)
                if args.debug:
                    print("[debug] API access token generated from refresh token")
            except Exception as exc:
                if args.debug:
                    print(
                        f"[debug] could not generate API access token ({exc}) — using public API"
                    )
        elif args.debug:
            print(
                "[debug] no refresh token stored — re-run steam-login to enable auth bypass"
            )

    results = build_leaderboard(
        year=args.year,
        my_id=my_id,
        top_n=args.top,
        max_workers=args.concurrency,
        debug=args.debug,
        api_token=api_token,
        filter_names=args.filter,
    )
    print_leaderboard(results, args.year)
