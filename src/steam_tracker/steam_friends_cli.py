import argparse

from . import steam_http
from .config import API_KEY
from .steam_api import (
    filter_by_display_name,
    get_friend_ids,
    get_player_summaries_bulk_full,
)
from .steam_auth import get_my_id
from .utils import truncate

_VISIBILITY = {1: "Private", 2: "Friends only", 3: "Public"}


def main() -> None:
    parser = argparse.ArgumentParser(description="List Steam friends with profile info")
    parser.add_argument(
        "--filter",
        "-f",
        nargs="+",
        metavar="NAME",
        help="Show only friends whose display name contains NAME (case-insensitive)",
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

    friend_ids = get_friend_ids(my_id)
    if not friend_ids:
        print("No friends found (check your Steam friends list privacy settings).")
        return

    players = get_player_summaries_bulk_full(friend_ids)
    players.sort(key=lambda p: p.get("personaname", "").lower())

    if args.filter:
        entries = [(p["steamid"], p.get("personaname", "")) for p in players]
        matched_ids, unmatched = filter_by_display_name(entries, args.filter)
        if args.debug and unmatched:
            for term in unmatched:
                print(f"[debug] no friends matched filter term: {term!r}")
            searched = ", ".join(name for _, name in entries)
            print(f"[debug] friends searched ({len(entries)}): {searched}")
        matched_set = set(matched_ids)
        players = [p for p in players if p["steamid"] in matched_set]

    if not players:
        print("No friends match the filter.")
        return

    name_w, real_w, id_w, vis_w = 28, 22, 19, 13
    header = (
        f"{'Display Name':<{name_w}} "
        f"{'Real Name':<{real_w}} "
        f"{'Steam64 ID':<{id_w}} "
        f"{'Visibility':<{vis_w}}"
    )
    print(f"\n{header}")
    print("─" * len(header))

    for player in players:
        display = truncate(player.get("personaname", player["steamid"]), name_w)
        real = truncate(player.get("realname", ""), real_w)
        steam_id = player["steamid"]
        vis = _VISIBILITY.get(player.get("communityvisibilitystate", 1), "Unknown")
        print(
            f"{display:<{name_w}} "
            f"{real or '—':<{real_w}} "
            f"{steam_id:<{id_w}} "
            f"{vis:<{vis_w}}"
        )

    print(f"\n  {len(players)} friend(s) listed.")
