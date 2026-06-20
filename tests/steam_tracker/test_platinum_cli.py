"""Tests for platinum_cli.py.

All external I/O (Steam API, DB, LLM, DOCX rendering) is monkeypatched.
Pure helpers (_build_pending, _pick_app) are tested directly.
main() is tested via a _run() helper that patches the module boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from docx import Document

from steam_tracker import platinum_cli
from steam_tracker.contracts import (
    GuideContent,
    LLMStrategyOutput,
    StrategyItem,
    StrategySection,
    UserAnnotations,
)
from steam_tracker.platinum_cli import _build_pending, _pick_app
from steam_tracker.strategy_generator import StrategyGenerationError

_MY_ID = "76561198000000001"
_APP_ID = 268050
_GAME_NAME = "The Evil Within"

_SCHEMA = [
    {
        "name": "ACH_1",
        "displayName": "A Lost Soul",
        "description": "Get lost.",
        "hidden": 0,
        "icon": "",
    },
    {
        "name": "ACH_2",
        "displayName": "A Winner",
        "description": "Win something.",
        "hidden": 0,
        "icon": "",
    },
    {
        "name": "ACH_3",
        "displayName": "Secret One",
        "description": "",
        "hidden": 1,
        "icon": "",
    },
]

_PLAYER = [
    {"apiname": "ACH_1", "achieved": 0, "unlocktime": 0, "description": ""},
    {
        "apiname": "ACH_2",
        "achieved": 1,
        "unlocktime": 1700000000,
        "description": "Win something.",
    },
    {"apiname": "ACH_3", "achieved": 0, "unlocktime": 0, "description": ""},
]

_DEFAULT = object()


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_output() -> LLMStrategyOutput:
    return LLMStrategyOutput(
        total_runs=2,
        estimated_hours="20-30",
        summary="Complete on Survival difficulty.",
        sections=[
            StrategySection(
                title="Story",
                category="story",
                overview="Follow the story.",
                items=[
                    StrategyItem(
                        api_name="ACH_1",
                        display_name="A Lost Soul",
                        tip="Just play.",
                        guide_link="",
                    ),
                    StrategyItem(
                        api_name="ACH_3",
                        display_name="Secret One",
                        tip="Hidden trick.",
                        guide_link="",
                    ),
                ],
            ),
        ],
        recommended_order=["Run 1: Survival", "Run 2: Mop-up"],
    )


def _make_guide() -> GuideContent:
    return GuideContent(
        source="https://steamcommunity.com/app/268050/guides",
        raw_text="Step 1: Start the game on Survival.",
    )


def _make_strategy_row(output: LLMStrategyOutput | None = None) -> MagicMock:
    row = MagicMock()
    row.strategy_json = (output or _make_output()).model_dump()
    row.app_id = _APP_ID
    return row


def _make_guide_db_row() -> MagicMock:
    row = MagicMock()
    row.app_id = _APP_ID
    row.source = "https://steamcommunity.com/app/268050/guides"
    row.raw_text = "Step 1: Start the game on Survival."
    return row


def _make_gen_cls(return_value=None, side_effect=None):
    """Return a zero-arg callable whose instance has an AsyncMock generate method."""
    mock_gen = MagicMock()
    if side_effect is not None:
        mock_gen.generate = AsyncMock(side_effect=side_effect)
    else:
        mock_gen.generate = AsyncMock(return_value=return_value or _make_output())
    return lambda: mock_gen


def _blank_annotations() -> UserAnnotations:
    return UserAnnotations(
        docx_path="", added_lines=[], modified_lines=[], deleted_lines=[]
    )


def _run(
    monkeypatch,
    argv=None,
    *,
    my_id: str | None = _MY_ID,
    search_results=_DEFAULT,
    schema=_DEFAULT,
    player=_DEFAULT,
    guide=_DEFAULT,
    strategy_row=_DEFAULT,
    guide_db_row=_DEFAULT,
    user_input: str = "1",
    render_docx_fn=None,
    fetch_guide_fn=None,
    extract_annotations_fn=None,
    save_guide_fn=None,
    save_strategy_mock=None,
    generator_cls=None,
    search_apps_fn=None,
) -> MagicMock:
    """Run platinum_cli.main() with all external I/O monkeypatched.

    Returns the save_strategy mock so callers can assert call count/args.
    """
    if search_results is _DEFAULT:
        search_results = [{"id": _APP_ID, "name": _GAME_NAME}]
    if schema is _DEFAULT:
        schema = (_GAME_NAME, _SCHEMA)
    if player is _DEFAULT:
        player = _PLAYER
    if guide is _DEFAULT:
        guide = _make_guide()
    if strategy_row is _DEFAULT:
        strategy_row = _make_strategy_row()
    if guide_db_row is _DEFAULT:
        guide_db_row = _make_guide_db_row()

    mock_session = MagicMock()
    mock_save_strategy = save_strategy_mock or MagicMock()

    monkeypatch.setattr(platinum_cli, "init_db", lambda: None)
    monkeypatch.setattr(platinum_cli, "get_session", lambda: mock_session)
    monkeypatch.setattr(platinum_cli, "get_my_id", lambda *_: my_id)
    monkeypatch.setattr(
        platinum_cli, "search_apps", search_apps_fn or (lambda _: search_results)
    )
    monkeypatch.setattr(platinum_cli, "get_game_schema", lambda _: schema)
    monkeypatch.setattr(platinum_cli, "get_all_player_achievements", lambda *_: player)
    monkeypatch.setattr(
        platinum_cli,
        "fetch_guide",
        fetch_guide_fn or MagicMock(return_value=guide),
    )
    monkeypatch.setattr(
        platinum_cli, "StrategyGenerator", generator_cls or _make_gen_cls()
    )
    monkeypatch.setattr(
        platinum_cli,
        "save_guide",
        save_guide_fn or MagicMock(return_value=guide_db_row),
    )
    monkeypatch.setattr(platinum_cli, "save_strategy", mock_save_strategy)
    monkeypatch.setattr(platinum_cli, "get_latest_strategy", lambda *_: strategy_row)
    monkeypatch.setattr(platinum_cli, "get_latest_guide", lambda *_: guide_db_row)
    monkeypatch.setattr(platinum_cli, "render_docx", render_docx_fn or MagicMock())
    monkeypatch.setattr(
        platinum_cli,
        "extract_annotations",
        extract_annotations_fn or (lambda *_: _blank_annotations()),
    )
    monkeypatch.setattr("builtins.input", lambda _: user_input)

    if argv is None:
        argv = ["--app-id", str(_APP_ID)]
    monkeypatch.setattr(sys, "argv", ["steam-platinum", *argv])

    platinum_cli.main()
    return mock_save_strategy


# ── _build_pending ─────────────────────────────────────────────────────────────


def test_build_pending_excludes_achieved():
    pending = _build_pending(_SCHEMA, _PLAYER)
    assert "ACH_2" not in [p.api_name for p in pending]


def test_build_pending_includes_not_achieved():
    pending = _build_pending(_SCHEMA, _PLAYER)
    api_names = [p.api_name for p in pending]
    assert "ACH_1" in api_names
    assert "ACH_3" in api_names


def test_build_pending_count():
    assert len(_build_pending(_SCHEMA, _PLAYER)) == 2


def test_build_pending_hidden_flag():
    pending = _build_pending(_SCHEMA, _PLAYER)
    by_name = {p.api_name: p for p in pending}
    assert by_name["ACH_3"].is_hidden is True
    assert by_name["ACH_1"].is_hidden is False


def test_build_pending_schema_idx_starts_at_1():
    pending = _build_pending(_SCHEMA, _PLAYER)
    assert pending[0].schema_idx == 1


def test_build_pending_schema_idx_follows_schema_position():
    pending = _build_pending(_SCHEMA, _PLAYER)
    assert pending[0].api_name == "ACH_1"
    assert pending[0].schema_idx == 1
    assert pending[1].api_name == "ACH_3"
    assert pending[1].schema_idx == 3


def test_build_pending_all_achieved_returns_empty():
    all_won = [
        {"apiname": a["name"], "achieved": 1, "unlocktime": 100, "description": ""}
        for a in _SCHEMA
    ]
    assert _build_pending(_SCHEMA, all_won) == []


def test_build_pending_missing_player_entry_treated_as_not_achieved():
    partial = [
        {"apiname": "ACH_1", "achieved": 1, "unlocktime": 100, "description": ""},
        {"apiname": "ACH_2", "achieved": 1, "unlocktime": 200, "description": ""},
    ]
    pending = _build_pending(_SCHEMA, partial)
    assert len(pending) == 1
    assert pending[0].api_name == "ACH_3"


def test_build_pending_uses_schema_display_name():
    pending = _build_pending(_SCHEMA, _PLAYER)
    assert pending[0].display_name == "A Lost Soul"


def test_build_pending_falls_back_to_api_name_when_no_display_name():
    schema = [
        {"name": "ACH_X", "displayName": "", "description": "", "hidden": 0, "icon": ""}
    ]
    player: list[dict] = []
    pending = _build_pending(schema, player)
    assert pending[0].display_name == "ACH_X"


def test_build_pending_description_from_player_overrides_schema():
    schema = [
        {
            "name": "ACH_1",
            "displayName": "D",
            "description": "schema desc",
            "hidden": 0,
            "icon": "",
        }
    ]
    player = [
        {
            "apiname": "ACH_1",
            "achieved": 0,
            "unlocktime": 0,
            "description": "player desc",
        }
    ]
    pending = _build_pending(schema, player)
    assert pending[0].description == "player desc"


# ── _pick_app ─────────────────────────────────────────────────────────────────


def test_pick_app_single_result_no_prompt(monkeypatch):
    monkeypatch.setattr(
        platinum_cli, "search_apps", lambda _: [{"id": 1, "name": "Game"}]
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda _: (_ for _ in ()).throw(AssertionError("should not prompt")),
    )
    assert _pick_app("Game") == (1, "Game")


def test_pick_app_no_results_returns_none(monkeypatch):
    monkeypatch.setattr(platinum_cli, "search_apps", lambda _: [])
    assert _pick_app("Unknown") is None


def test_pick_app_multiple_results_user_picks(monkeypatch):
    results = [{"id": 1, "name": "Game A"}, {"id": 2, "name": "Game B"}]
    monkeypatch.setattr(platinum_cli, "search_apps", lambda _: results)
    monkeypatch.setattr("builtins.input", lambda _: "2")
    assert _pick_app("Game") == (2, "Game B")


def test_pick_app_empty_input_returns_none(monkeypatch):
    results = [{"id": 1, "name": "Game A"}, {"id": 2, "name": "Game B"}]
    monkeypatch.setattr(platinum_cli, "search_apps", lambda _: results)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert _pick_app("Game") is None


def test_pick_app_out_of_range_returns_none(monkeypatch):
    results = [{"id": 1, "name": "Game A"}, {"id": 2, "name": "Game B"}]
    monkeypatch.setattr(platinum_cli, "search_apps", lambda _: results)
    monkeypatch.setattr("builtins.input", lambda _: "99")
    assert _pick_app("Game") is None


def test_pick_app_non_numeric_returns_none(monkeypatch):
    results = [{"id": 1, "name": "Game A"}, {"id": 2, "name": "Game B"}]
    monkeypatch.setattr(platinum_cli, "search_apps", lambda _: results)
    monkeypatch.setattr("builtins.input", lambda _: "abc")
    assert _pick_app("Game") is None


# ── main() — normal run ───────────────────────────────────────────────────────


def test_main_normal_run_calls_render_docx(monkeypatch):
    mock_render = MagicMock()
    _run(monkeypatch, render_docx_fn=mock_render)
    assert mock_render.called


def test_main_default_output_path_contains_slug_and_app_id(monkeypatch):
    mock_render = MagicMock()
    _run(monkeypatch, render_docx_fn=mock_render)
    path_str = str(mock_render.call_args.args[2])
    assert "the-evil-within" in path_str
    assert str(_APP_ID) in path_str


def test_main_custom_output_path(monkeypatch, tmp_path):
    out = tmp_path / "my_guide.docx"
    mock_render = MagicMock()
    _run(
        monkeypatch,
        argv=["--app-id", str(_APP_ID), "--output", str(out)],
        render_docx_fn=mock_render,
    )
    assert mock_render.call_args.args[2] == out


def test_main_saves_strategy(monkeypatch):
    mock_save = MagicMock()
    _run(monkeypatch, save_strategy_mock=mock_save)
    mock_save.assert_called_once()


def test_main_saves_guide_when_guide_has_text(monkeypatch):
    mock_save_guide = MagicMock(return_value=_make_guide_db_row())
    _run(monkeypatch, save_guide_fn=mock_save_guide)
    assert mock_save_guide.called


def test_main_no_guide_skips_fetch_and_save(monkeypatch):
    mock_fetch = MagicMock(return_value=_make_guide())
    mock_save_guide = MagicMock(return_value=_make_guide_db_row())
    _run(
        monkeypatch,
        argv=["--app-id", str(_APP_ID), "--no-guide"],
        fetch_guide_fn=mock_fetch,
        save_guide_fn=mock_save_guide,
    )
    assert not mock_fetch.called
    assert not mock_save_guide.called


def test_main_query_arg_uses_search(monkeypatch):
    search_called: list[str] = []
    _run(
        monkeypatch,
        argv=[_GAME_NAME],
        search_apps_fn=lambda q: (
            search_called.append(q) or [{"id": _APP_ID, "name": _GAME_NAME}]
        ),
    )
    assert search_called


def test_main_no_schema_exits_early(monkeypatch):
    calls = []
    _run(
        monkeypatch, schema=(_GAME_NAME, []), render_docx_fn=lambda *_: calls.append(1)
    )
    assert not calls


def test_main_no_steam_id_exits_early(monkeypatch):
    calls = []
    _run(monkeypatch, my_id=None, render_docx_fn=lambda *_: calls.append(1))
    assert not calls


def test_main_private_profile_exits_early(monkeypatch):
    calls = []
    _run(monkeypatch, player=None, render_docx_fn=lambda *_: calls.append(1))
    assert not calls


def test_main_all_achieved_exits_early(monkeypatch, capsys):
    all_won = [
        {"apiname": a["name"], "achieved": 1, "unlocktime": 100, "description": ""}
        for a in _SCHEMA
    ]
    calls = []
    _run(monkeypatch, player=all_won, render_docx_fn=lambda *_: calls.append(1))
    assert not calls
    assert "Platinum" in capsys.readouterr().out


def test_main_strategy_error_exits_gracefully(monkeypatch, capsys):
    err = StrategyGenerationError(
        "test", attempts=1, cause=RuntimeError("LLM call failed")
    )
    calls = []
    _run(
        monkeypatch,
        generator_cls=_make_gen_cls(side_effect=err),
        render_docx_fn=lambda *_: calls.append(1),
    )
    assert not calls
    assert "failed" in capsys.readouterr().out


def test_main_no_args_prints_help_and_returns(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["steam-platinum"])
    platinum_cli.main()


# ── main() — refine branch ────────────────────────────────────────────────────


def _make_refine_docx(tmp_path: Path) -> Path:
    """Minimal DOCX for --refine tests."""
    path = tmp_path / "guide.docx"
    doc = Document()
    doc.add_paragraph("Complete on Survival difficulty.")
    doc.save(str(path))
    return path


def test_main_refine_calls_render_docx_at_refine_path(monkeypatch, tmp_path):
    docx_path = _make_refine_docx(tmp_path)
    mock_render = MagicMock()
    _run(
        monkeypatch,
        argv=["--app-id", str(_APP_ID), "--refine", str(docx_path)],
        render_docx_fn=mock_render,
    )
    assert mock_render.call_args.args[2] == docx_path


def test_main_refine_with_output_overrides_path(monkeypatch, tmp_path):
    docx_path = _make_refine_docx(tmp_path)
    out = tmp_path / "custom.docx"
    mock_render = MagicMock()
    _run(
        monkeypatch,
        argv=[
            "--app-id",
            str(_APP_ID),
            "--refine",
            str(docx_path),
            "--output",
            str(out),
        ],
        render_docx_fn=mock_render,
    )
    assert mock_render.call_args.args[2] == out


def test_main_refine_missing_file_exits_early(monkeypatch, tmp_path, capsys):
    calls = []
    _run(
        monkeypatch,
        argv=["--app-id", str(_APP_ID), "--refine", str(tmp_path / "ghost.docx")],
        render_docx_fn=lambda *_: calls.append(1),
    )
    assert not calls
    assert "not found" in capsys.readouterr().out.lower()


def test_main_refine_no_cached_strategy_exits_early(monkeypatch, tmp_path, capsys):
    docx_path = _make_refine_docx(tmp_path)
    calls = []
    _run(
        monkeypatch,
        argv=["--app-id", str(_APP_ID), "--refine", str(docx_path)],
        strategy_row=None,
        render_docx_fn=lambda *_: calls.append(1),
    )
    assert not calls
    assert "--refine" in capsys.readouterr().out


def test_main_refine_passes_annotations_to_generator(monkeypatch, tmp_path):
    docx_path = _make_refine_docx(tmp_path)
    annotations_obj = UserAnnotations(
        docx_path=str(docx_path),
        added_lines=["My personal note"],
        modified_lines=[],
        deleted_lines=[],
    )
    mock_gen = MagicMock()
    mock_gen.generate = AsyncMock(return_value=_make_output())

    _run(
        monkeypatch,
        argv=["--app-id", str(_APP_ID), "--refine", str(docx_path)],
        generator_cls=lambda: mock_gen,
        extract_annotations_fn=lambda *_: annotations_obj,
    )
    # generate(app_id, game_name, pending, guide, annotations) — annotations is positional index 4
    assert mock_gen.generate.call_args.args[4] is annotations_obj


def test_main_refine_skips_guide_fetch(monkeypatch, tmp_path):
    docx_path = _make_refine_docx(tmp_path)
    mock_fetch = MagicMock(return_value=_make_guide())
    _run(
        monkeypatch,
        argv=["--app-id", str(_APP_ID), "--refine", str(docx_path)],
        fetch_guide_fn=mock_fetch,
    )
    assert not mock_fetch.called
