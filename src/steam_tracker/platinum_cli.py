"""CLI entry point for steam-platinum: AI-powered achievement guide generator."""

from __future__ import annotations

import argparse
import asyncio

from rich.console import Console

from . import steam_http
from .achievement_guide import fetch_guide
from .contracts import GuideContent, LLMStrategyOutput, PendingAchievement
from .db import get_session, init_db
from .repository import save_guide, save_strategy
from .settings import LLM_MODEL
from .steam_api import get_all_player_achievements, get_game_schema, search_apps
from .steam_auth import get_my_id
from .strategy_generator import StrategyGenerationError, StrategyGenerator

console = Console(highlight=False, markup=False)

_CATEGORY_LABEL: dict[str, str] = {
    "missable": "MISSABLE",
    "story": "STORY",
    "grind": "GRIND",
    "collectible": "COLLECTIBLE",
    "difficulty": "DIFFICULTY",
    "misc": "MISC",
}


def _pick_app(query: str) -> tuple[int, str] | None:
    results = search_apps(query)
    if not results:
        console.print(f"No games found matching '{query}'.")
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
    console.print("Invalid selection.")
    return None


def _build_pending(schema: list[dict], player: list[dict]) -> list[PendingAchievement]:
    player_map = {a["apiname"]: a for a in player}
    pending = []
    for idx, ach in enumerate(schema, start=1):
        key = ach["name"]
        p = player_map.get(key, {})
        if p.get("achieved", 0):
            continue
        pending.append(
            PendingAchievement(
                api_name=key,
                display_name=ach.get("displayName") or key,
                description=p.get("description") or ach.get("description") or "",
                is_hidden=bool(ach.get("hidden")),
                schema_idx=idx,
                icon_url=ach.get("icon", ""),
            )
        )
    return pending


def _print_strategy(output: LLMStrategyOutput, game_name: str) -> None:
    hr = "─" * 60
    console.print(f"\n{hr}")
    console.print(f"  {game_name} — Platinum Strategy")
    console.print(
        f"  Minimum runs: {output.total_runs}  •  Est. hours: {output.estimated_hours}"
    )
    console.print(f"{hr}\n")
    console.print(output.summary)

    for section in output.sections:
        label = _CATEGORY_LABEL.get(section.category, section.category.upper())
        console.print(f"\n[{label}]  {section.title}")
        console.print(f"  {section.overview}")
        for item in section.items:
            console.print(f"\n  o  {item.display_name}")
            console.print(f"     {item.tip}")
            if item.guide_link:
                console.print(f"     -> {item.guide_link}")

    console.print(f"\n{hr}")
    console.print("  Recommended Order")
    console.print(hr)
    for i, step in enumerate(output.recommended_order, start=1):
        console.print(f"  {i:2}. {step}")
    console.print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an AI-powered platinum achievement guide."
    )
    parser.add_argument("query", nargs="?", help="Game name to search for")
    parser.add_argument(
        "--app-id", type=int, metavar="ID", help="Use App ID directly (skips search)"
    )
    parser.add_argument(
        "--no-guide",
        action="store_true",
        help="Skip web guide fetch; use AI training knowledge only",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Print HTTP errors and guide source URLs",
    )
    args = parser.parse_args()

    if not args.query and not args.app_id:
        parser.print_help()
        return

    steam_http.DEBUG = args.debug

    # Resolve app_id + schema
    if args.app_id:
        app_id = args.app_id
        game_name, schema = get_game_schema(app_id)
        if not game_name:
            console.print(f"No schema found for App ID {app_id}.")
            return
    else:
        result = _pick_app(args.query)
        if result is None:
            return
        app_id, _ = result
        game_name, schema = get_game_schema(app_id)

    if not schema:
        console.print(f"'{game_name}' has no achievement schema.")
        return

    init_db()
    session = get_session()
    try:
        my_id = get_my_id(args.debug)
        if not my_id:
            console.print("Could not determine your Steam ID. Run steam-login first.")
            return

        player = get_all_player_achievements(my_id, app_id)
        if player is None:
            console.print(
                f"Could not fetch achievements for '{game_name}'. Profile may be private."
            )
            return

        pending = _build_pending(schema, player)
        total = len(schema)
        earned = total - len(pending)

        if not pending:
            console.print(
                f"All {total} achievements earned in '{game_name}'. Platinum!"
            )
            return

        console.print(
            f"\n{game_name}  |  {earned}/{total} achieved  |  {len(pending)} remaining\n"
        )

        guide: GuideContent | None = None
        if not args.no_guide:
            console.print("Fetching achievement guide...")
            guide = fetch_guide(app_id, game_name, debug=args.debug)
            if guide.raw_text:
                console.print(f"  Source: {guide.source}")
            else:
                console.print("  No guide found — AI will use training knowledge.")

        console.print("Generating platinum strategy...")
        try:
            gen = StrategyGenerator()
            output = asyncio.run(gen.generate(app_id, game_name, pending, guide))
        except StrategyGenerationError as exc:
            console.print(f"Strategy generation failed: {exc}")
            return

        guide_row = None
        if guide and guide.raw_text:
            guide_row = save_guide(session, app_id, guide.source, guide.raw_text)
        save_strategy(session, app_id, guide_row, LLM_MODEL, output.model_dump())
        console.print("Strategy saved to database.\n")

        _print_strategy(output, game_name)

    finally:
        session.close()
