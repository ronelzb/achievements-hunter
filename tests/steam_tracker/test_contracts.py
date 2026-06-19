from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from steam_tracker.contracts import (
    GuideContent,
    LLMStrategyOutput,
    PendingAchievement,
    StrategyItem,
    StrategyResult,
    StrategySection,
    UserAnnotations,
)

# ── PendingAchievement ────────────────────────────────────────────────────────


def test_pending_achievement_valid():
    a = PendingAchievement(
        api_name="ACH_01",
        display_name="First Blood",
        description="Kill an enemy",
        is_hidden=False,
        schema_idx=1,
        icon_url="https://cdn.example.com/icon.jpg",
    )
    assert a.api_name == "ACH_01"
    assert a.is_hidden is False


def test_pending_achievement_empty_description_allowed():
    a = PendingAchievement(
        api_name="ACH_HIDDEN",
        display_name="???",
        description="",
        is_hidden=True,
        schema_idx=5,
        icon_url="",
    )
    assert a.description == ""
    assert a.icon_url == ""


def test_pending_achievement_missing_field_raises():
    with pytest.raises(ValidationError):
        PendingAchievement.model_validate(
            {
                "api_name": "X",
                "display_name": "Y",
                "is_hidden": False,
                "schema_idx": 1,
                "icon_url": "",
            }
        )


# ── GuideContent ──────────────────────────────────────────────────────────────


def test_guide_content_valid():
    g = GuideContent(
        source="https://truesteamachievements.com/game/foo", raw_text="some guide text"
    )
    assert g.source.startswith("https://")
    assert g.raw_text == "some guide text"


def test_guide_content_empty_raw_text_allowed():
    g = GuideContent(source="fallback", raw_text="")
    assert g.raw_text == ""


# ── StrategyItem ──────────────────────────────────────────────────────────────


def test_strategy_item_guide_link_defaults_to_empty():
    item = StrategyItem(
        api_name="ACH_01", display_name="First Blood", tip="Kill something"
    )
    assert item.guide_link == ""


def test_strategy_item_with_guide_link():
    item = StrategyItem(
        api_name="ACH_01",
        display_name="First Blood",
        tip="Kill something",
        guide_link="https://truesteamachievements.com/a/123",
    )
    assert item.guide_link == "https://truesteamachievements.com/a/123"


# ── StrategySection ───────────────────────────────────────────────────────────


def test_strategy_section_valid_categories():
    for cat in ("missable", "story", "grind", "collectible", "difficulty", "misc"):
        s = StrategySection(title="T", category=cat, overview="O", items=[])
        assert s.category == cat


def test_strategy_section_invalid_category_raises():
    with pytest.raises(ValidationError):
        StrategySection.model_validate(
            {"title": "T", "category": "unknown", "overview": "O", "items": []}
        )


def test_strategy_section_contains_items():
    item = StrategyItem(api_name="A", display_name="B", tip="C")
    section = StrategySection(
        title="Missables", category="missable", overview="Watch out", items=[item]
    )
    assert len(section.items) == 1
    assert section.items[0].api_name == "A"


# ── LLMStrategyOutput ─────────────────────────────────────────────────────────


def _make_output(**overrides) -> dict:
    base = {
        "total_runs": 2,
        "estimated_hours": "25-40",
        "summary": "Complete on Survival first.",
        "sections": [
            {
                "title": "Missables",
                "category": "missable",
                "overview": "Do not miss these.",
                "items": [{"api_name": "A", "display_name": "B", "tip": "C"}],
            }
        ],
        "recommended_order": ["Play on Survival", "Mop up collectibles"],
    }
    base.update(overrides)
    return base


def test_llm_strategy_output_valid():
    out = LLMStrategyOutput(**_make_output())
    assert out.total_runs == 2
    assert out.estimated_hours == "25-40"
    assert len(out.sections) == 1
    assert len(out.recommended_order) == 2


def test_llm_strategy_output_total_runs_must_be_at_least_1():
    with pytest.raises(ValidationError):
        LLMStrategyOutput(**_make_output(total_runs=0))


def test_llm_strategy_output_negative_total_runs_raises():
    with pytest.raises(ValidationError):
        LLMStrategyOutput(**_make_output(total_runs=-1))


def test_llm_strategy_output_json_round_trip():
    out = LLMStrategyOutput(**_make_output())
    json_str = out.model_dump_json()
    restored = LLMStrategyOutput.model_validate_json(json_str)
    assert restored == out


def test_llm_strategy_output_empty_sections_allowed():
    out = LLMStrategyOutput(**_make_output(sections=[], recommended_order=[]))
    assert out.sections == []


# ── UserAnnotations ───────────────────────────────────────────────────────────


def test_user_annotations_valid():
    ua = UserAnnotations(
        docx_path="guide.docx",
        added_lines=["my note"],
        modified_lines=[],
        deleted_lines=["old tip"],
    )
    assert ua.docx_path == "guide.docx"
    assert ua.added_lines == ["my note"]
    assert ua.deleted_lines == ["old tip"]


def test_user_annotations_all_empty_lists_allowed():
    ua = UserAnnotations(
        docx_path="x.docx", added_lines=[], modified_lines=[], deleted_lines=[]
    )
    assert ua.added_lines == []


# ── StrategyResult ────────────────────────────────────────────────────────────


def test_strategy_result_valid():
    out = LLMStrategyOutput(**_make_output())
    result = StrategyResult(
        app_id=268050,
        game_name="The Evil Within",
        model="claude-sonnet-4-6",
        output=out,
        created_at=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert result.app_id == 268050
    assert result.is_refinement is False


def test_strategy_result_is_refinement_defaults_to_false():
    out = LLMStrategyOutput(**_make_output())
    result = StrategyResult(
        app_id=1,
        game_name="Game",
        model="m",
        output=out,
        created_at=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert result.is_refinement is False


def test_strategy_result_refinement_flag():
    out = LLMStrategyOutput(**_make_output())
    result = StrategyResult(
        app_id=1,
        game_name="Game",
        model="m",
        output=out,
        created_at=datetime(2026, 6, 18, tzinfo=UTC),
        is_refinement=True,
    )
    assert result.is_refinement is True


def test_strategy_result_json_round_trip():
    out = LLMStrategyOutput(**_make_output())
    result = StrategyResult(
        app_id=268050,
        game_name="The Evil Within",
        model="claude-sonnet-4-6",
        output=out,
        created_at=datetime(2026, 6, 18, tzinfo=UTC),
    )
    restored = StrategyResult.model_validate_json(result.model_dump_json())
    assert restored == result
