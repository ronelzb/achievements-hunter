import json

import pytest

from steam_tracker.contracts import (
    GuideContent,
    LLMStrategyOutput,
    PendingAchievement,
    UserAnnotations,
)
from steam_tracker.strategy_generator import StrategyGenerationError, StrategyGenerator

# ── Helpers ───────────────────────────────────────────────────────────────────


def _ach(
    api_name: str,
    display_name: str,
    description: str = "Do it",
    is_hidden: bool = False,
):
    return PendingAchievement(
        api_name=api_name,
        display_name=display_name,
        description=description,
        is_hidden=is_hidden,
        schema_idx=0,
        icon_url="",
    )


def _valid_output_json(total_runs: int = 2) -> str:
    return json.dumps(
        {
            "total_runs": total_runs,
            "estimated_hours": "10-20",
            "summary": "Beat on Nightmare first.",
            "sections": [
                {
                    "title": "Missables",
                    "category": "missable",
                    "overview": "Do not miss these.",
                    "items": [
                        {
                            "api_name": "ACH_01",
                            "display_name": "First Blood",
                            "tip": "Kill during chapter 1",
                            "guide_link": "",
                        }
                    ],
                }
            ],
            "recommended_order": ["Play on Nightmare"],
        }
    )


class _StubProvider:
    """Returns pre-set responses or raises on demand; records every call."""

    def __init__(self, responses: list[str | Exception]):
        self._queue = list(responses)
        self.calls: list[tuple[str, str]] = []  # (system, user) per invocation

    async def complete(self, system: str, user: str, /) -> str:
        self.calls.append((system, user))
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# ── _strip_fences ─────────────────────────────────────────────────────────────


def test_strip_fences_plain_json_unchanged():
    raw = '{"key": "value"}'
    assert StrategyGenerator._strip_fences(raw) == raw


def test_strip_fences_removes_json_fence():
    raw = "```json\n{}\n```"
    assert StrategyGenerator._strip_fences(raw) == "{}"


def test_strip_fences_removes_plain_fence():
    raw = "```\n{}\n```"
    assert StrategyGenerator._strip_fences(raw) == "{}"


def test_strip_fences_only_opening_fence_unchanged():
    raw = "```json\n{}"
    result = StrategyGenerator._strip_fences(raw)
    assert "{}" in result


def test_strip_fences_strips_surrounding_whitespace():
    raw = "  \n{}\n  "
    assert StrategyGenerator._strip_fences(raw) == "{}"


# ── _build_user_prompt ────────────────────────────────────────────────────────


def test_build_user_prompt_contains_game_info():
    pending = [_ach("ACH_01", "First Blood")]
    prompt = StrategyGenerator._build_user_prompt(
        268050, "The Evil Within", pending, None, None
    )
    assert "The Evil Within" in prompt
    assert "268050" in prompt


def test_build_user_prompt_lists_achievements():
    pending = [_ach("ACH_01", "First Blood"), _ach("ACH_02", "Survivor")]
    prompt = StrategyGenerator._build_user_prompt(1, "Game", pending, None, None)
    assert "ACH_01" in prompt
    assert "First Blood" in prompt
    assert "ACH_02" in prompt
    assert "Survivor" in prompt


def test_build_user_prompt_hidden_achievement_shows_fallback():
    pending = [_ach("ACH_HIDDEN", "???", description="", is_hidden=True)]
    prompt = StrategyGenerator._build_user_prompt(1, "Game", pending, None, None)
    assert "[hidden achievement]" in prompt


def test_build_user_prompt_with_guide_text():
    guide = GuideContent(
        source="https://example.com", raw_text="Detailed walkthrough here."
    )
    prompt = StrategyGenerator._build_user_prompt(1, "Game", [], guide, None)
    assert "Detailed walkthrough here." in prompt


def test_build_user_prompt_no_guide_uses_fallback():
    prompt = StrategyGenerator._build_user_prompt(1, "Game", [], None, None)
    assert "No guide text available" in prompt


def test_build_user_prompt_empty_guide_raw_text_uses_fallback():
    guide = GuideContent(source="fallback", raw_text="")
    prompt = StrategyGenerator._build_user_prompt(1, "Game", [], guide, None)
    assert "No guide text available" in prompt


def test_build_user_prompt_without_annotations_has_no_annotations_section():
    prompt = StrategyGenerator._build_user_prompt(1, "Game", [], None, None)
    assert "USER ANNOTATIONS" not in prompt


def test_build_user_prompt_with_annotations_includes_diff():
    ann = UserAnnotations(
        docx_path="guide.docx",
        added_lines=["new note"],
        modified_lines=["changed tip"],
        deleted_lines=["old tip"],
    )
    prompt = StrategyGenerator._build_user_prompt(1, "Game", [], None, ann)
    assert "USER ANNOTATIONS" in prompt
    assert "new note" in prompt
    assert "changed tip" in prompt
    assert "old tip" in prompt


def test_build_user_prompt_empty_annotations_shows_none():
    ann = UserAnnotations(
        docx_path="x.docx", added_lines=[], modified_lines=[], deleted_lines=[]
    )
    prompt = StrategyGenerator._build_user_prompt(1, "Game", [], None, ann)
    assert "USER ANNOTATIONS" in prompt
    assert "none" in prompt


def test_build_user_prompt_achievement_count_in_header():
    pending = [_ach("A1", "Ach1"), _ach("A2", "Ach2"), _ach("A3", "Ach3")]
    prompt = StrategyGenerator._build_user_prompt(1, "Game", pending, None, None)
    assert "3 remaining" in prompt


# ── generate (async) ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_generate_returns_valid_output_on_first_try():
    stub = _StubProvider([_valid_output_json()])
    gen = StrategyGenerator(provider=stub)
    pending = [_ach("ACH_01", "First Blood")]
    result = await gen.generate(268050, "The Evil Within", pending, None)
    assert isinstance(result, LLMStrategyOutput)
    assert result.total_runs == 2


@pytest.mark.anyio
async def test_generate_strips_fences_before_parsing():
    raw = f"```json\n{_valid_output_json()}\n```"
    stub = _StubProvider([raw])
    gen = StrategyGenerator(provider=stub)
    result = await gen.generate(1, "Game", [], None)
    assert isinstance(result, LLMStrategyOutput)


@pytest.mark.anyio
async def test_generate_retries_on_invalid_json_then_succeeds():
    stub = _StubProvider(["not json at all", _valid_output_json()])
    gen = StrategyGenerator(provider=stub)
    result = await gen.generate(1, "Game", [], None, max_retries=3)
    assert isinstance(result, LLMStrategyOutput)


@pytest.mark.anyio
async def test_generate_retries_on_validation_error_then_succeeds():
    invalid = json.dumps({"total_runs": 0})  # fails ge=1 constraint
    stub = _StubProvider([invalid, _valid_output_json()])
    gen = StrategyGenerator(provider=stub)
    result = await gen.generate(1, "Game", [], None, max_retries=3)
    assert isinstance(result, LLMStrategyOutput)


@pytest.mark.anyio
async def test_generate_retries_on_value_error_then_succeeds():
    stub = _StubProvider([ValueError("rate limit"), _valid_output_json()])
    gen = StrategyGenerator(provider=stub)
    result = await gen.generate(1, "Game", [], None, max_retries=3)
    assert isinstance(result, LLMStrategyOutput)


@pytest.mark.anyio
async def test_generate_raises_after_all_retries_exhausted():
    stub = _StubProvider(["bad", "bad", "bad"])
    gen = StrategyGenerator(provider=stub)
    with pytest.raises(StrategyGenerationError) as exc_info:
        await gen.generate(1, "Game", [], None, max_retries=3)
    assert exc_info.value.attempts == 3
    assert "Game" in exc_info.value.context


@pytest.mark.anyio
async def test_generate_uses_annotations_in_refine_pass():
    """Verify that annotations flow into the user prompt."""
    ann = UserAnnotations(
        docx_path="guide.docx",
        added_lines=["my note"],
        modified_lines=[],
        deleted_lines=[],
    )
    stub = _StubProvider([_valid_output_json()])
    gen = StrategyGenerator(provider=stub)
    await gen.generate(1, "Game", [], None, annotations=ann)
    assert stub.calls, "provider was never called"
    _, user = stub.calls[0]
    assert "my note" in user
    assert "USER ANNOTATIONS" in user


@pytest.mark.anyio
async def test_generate_without_annotations_omits_annotations_block():
    stub = _StubProvider([_valid_output_json()])
    gen = StrategyGenerator(provider=stub)
    await gen.generate(1, "Game", [], None)
    _, user = stub.calls[0]
    assert "USER ANNOTATIONS" not in user
