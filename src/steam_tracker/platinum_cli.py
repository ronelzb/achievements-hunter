"""CLI entry point for steam-platinum: AI-powered achievement guide generator."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from . import steam_http
from .achievement_guide import fetch_guide
from .contracts import (
    GuideContent,
    LLMStrategyOutput,
    PendingAchievement,
    StrategyResult,
)
from .db import get_session, init_db
from .platinum_report import extract_annotations, render_docx, render_to_text
from .repository import get_latest_guide, get_latest_strategy, save_guide, save_strategy
from .settings import LLM_MODEL
from .steam_api import get_all_player_achievements, get_game_schema, search_apps
from .steam_auth import get_my_id
from .strategy_generator import StrategyGenerationError, StrategyGenerator
from .utils import game_slug

console = Console(highlight=False, markup=False)


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
        "--refine",
        "-r",
        metavar="PATH",
        help="Incorporate notes from an existing guide DOCX and regenerate",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        help="Override output DOCX path (default: {slug}_{appid}_guide.docx)",
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

    # Resolve game
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

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    elif args.refine:
        output_path = Path(args.refine)
    else:
        output_path = Path(f"{game_slug(game_name)}_{app_id}_guide.docx")

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
        guide_db_row = None
        annotations = None

        if args.refine:
            refine_path = Path(args.refine)
            if not refine_path.exists():
                console.print(f"File not found: {refine_path}")
                return

            strategy_row = get_latest_strategy(session, app_id)
            if strategy_row is None:
                console.print(
                    f"No cached strategy for '{game_name}'. Run without --refine first."
                )
                return

            baseline = render_to_text(
                LLMStrategyOutput.model_validate(strategy_row.strategy_json)
            )
            annotations = extract_annotations(refine_path, baseline)

            guide_db_row = get_latest_guide(session, app_id)
            if guide_db_row:
                guide = GuideContent(
                    source=guide_db_row.source, raw_text=guide_db_row.raw_text
                )
            console.print("Refining strategy with your annotations...")
        else:
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
            llm_output = asyncio.run(
                gen.generate(app_id, game_name, pending, guide, annotations)
            )
        except StrategyGenerationError as exc:
            console.print(f"Strategy generation failed: {exc}")
            return

        # Save guide (normal run only — refine reuses the cached guide row)
        if not args.refine and guide and guide.raw_text:
            guide_db_row = save_guide(session, app_id, guide.source, guide.raw_text)

        save_strategy(session, app_id, guide_db_row, LLM_MODEL, llm_output.model_dump())

        result = StrategyResult(
            app_id=app_id,
            game_name=game_name,
            model=LLM_MODEL,
            output=llm_output,
            created_at=datetime.now(UTC),
            is_refinement=bool(args.refine),
        )
        render_docx(result, pending, output_path)

        console.print("Strategy saved to database.")
        console.print(f"Guide written to: {output_path}")

    finally:
        session.close()
