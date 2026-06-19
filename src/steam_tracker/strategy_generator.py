"""Async strategy generator: prompt building, retry loop, Pydantic validation.

Follows the ecclesia-poc BillSummarizer pattern — the provider is injected at
construction time so tests can pass a stub without touching env vars.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from .contracts import (
    GuideContent,
    LLMStrategyOutput,
    PendingAchievement,
    UserAnnotations,
)
from .llm_provider import AsyncLLMProvider, async_provider_from_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — v1
# ---------------------------------------------------------------------------

_STRATEGY_SYSTEM_PROMPT_V1 = """\
You are a structured output engine for gaming achievement strategy.
Produce ONLY a JSON object matching this exact schema. No prose outside the JSON.

{
  "total_runs": 2,
  "estimated_hours": "25-40",
  "summary": "string",
  "sections": [
    {
      "title": "string",
      "category": "missable | story | grind | collectible | difficulty | misc",
      "overview": "string",
      "items": [
        {
          "api_name": "string",
          "display_name": "string",
          "tip": "string",
          "guide_link": "string or empty"
        }
      ]
    }
  ],
  "recommended_order": ["string"]
}

Rules:
- Every achievement in the pending list must appear in exactly one section.
- category must be one of: missable, story, grind, collectible, difficulty, misc.
- guide_link should be a TrueSteamAchievements URL when you can construct one
  confidently; otherwise use an empty string.
- total_runs must be >= 1.
- Do not add fields. Do not omit fields. Arrays may be empty."""

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class StrategyGenerationError(RuntimeError):
    """Raised when all retry attempts fail to produce a valid LLM output."""

    def __init__(self, context: str, attempts: int, cause: Exception) -> None:
        self.context = context
        self.attempts = attempts
        self.cause = cause
        super().__init__(
            f"Strategy generation failed for {context!r} after {attempts} attempt(s): {cause}"
        )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class StrategyGenerator:
    """Generates a platinum strategy using the configured async LLM provider.

    The provider is injected at construction time so tests can pass a stub
    without touching module globals or environment variables.

    Example::

        gen = StrategyGenerator()

        # normal run
        output = await gen.generate(app_id, game_name, pending, guide)

        # refine pass
        output = await gen.generate(
            app_id, game_name, pending, guide, annotations=annotations
        )
    """

    def __init__(self, provider: AsyncLLMProvider | None = None) -> None:
        self._provider = (
            provider if provider is not None else async_provider_from_settings()
        )

    @property
    def provider(self) -> AsyncLLMProvider:
        return self._provider

    @staticmethod
    def _strip_fences(raw: str) -> str:
        """Strip markdown code fences that some models add despite instructions."""
        stripped = raw.strip()
        if stripped.startswith("```"):
            first_newline = stripped.find("\n")
            if first_newline != -1:
                stripped = stripped[first_newline + 1 :]
            if stripped.endswith("```"):
                stripped = stripped[:-3].rstrip()
        return stripped

    @staticmethod
    def _build_user_prompt(
        app_id: int,
        game_name: str,
        pending: list[PendingAchievement],
        guide: GuideContent | None,
        annotations: UserAnnotations | None,
    ) -> str:
        lines: list[str] = [
            f"Game: {game_name} (App ID: {app_id})",
            f"Pending achievements ({len(pending)} remaining):",
            "",
        ]

        for i, ach in enumerate(pending, 1):
            desc = ach.description if ach.description else "[hidden achievement]"
            lines.append(f"{i}. {ach.api_name} | {ach.display_name} — {desc}")

        lines += [
            "",
            "--- GUIDE / WALKTHROUGH TEXT ---",
            guide.raw_text
            if (guide and guide.raw_text)
            else "No guide text available. Use your training knowledge.",
            "---",
        ]

        if annotations is not None:
            added = "\n".join(annotations.added_lines) or "none"
            modified = "\n".join(annotations.modified_lines) or "none"
            deleted = "\n".join(annotations.deleted_lines) or "none"
            lines += [
                "",
                "--- USER ANNOTATIONS (diff against previous strategy) ---",
                "ADDED (user wrote this):",
                added,
                "",
                "MODIFIED (user changed this):",
                modified,
                "",
                "DELETED (user intentionally removed this):",
                deleted,
                "",
                "Interpret deletions as follows:",
                "- achievement entry deleted → treat as completed or intentionally skipped",
                "- tip deleted → advice was wrong, inapplicable, or already known",
                "- section deleted → entire category is done or no longer relevant",
                "Incorporate all signals into the updated strategy.",
                "---",
            ]

        return "\n".join(lines)

    async def _call_with_retry(
        self,
        system: str,
        user: str,
        context: str,
        max_retries: int,
    ) -> LLMStrategyOutput:
        last_error: Exception = RuntimeError("No attempts made")

        for attempt in range(1, max_retries + 1):
            try:
                logger.debug("Attempt %d/%d — %s", attempt, max_retries, context)
                raw = await self._provider.complete(system, user)
                return LLMStrategyOutput.model_validate_json(self._strip_fences(raw))
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Attempt %d/%d failed for %s (%s): %s",
                    attempt,
                    max_retries,
                    context,
                    type(exc).__name__,
                    exc,
                )
                last_error = exc

        raise StrategyGenerationError(context, max_retries, last_error)

    async def generate(
        self,
        app_id: int,
        game_name: str,
        pending: list[PendingAchievement],
        guide: GuideContent | None,
        annotations: UserAnnotations | None = None,
        *,
        max_retries: int = 3,
    ) -> LLMStrategyOutput:
        """Generate (or refine) a platinum strategy for a game.

        Args:
            app_id:      Steam App ID.
            game_name:   Display name of the game.
            pending:     Unearned achievements to include in the strategy.
            guide:       Fetched guide text, or None when --no-guide is set.
            annotations: User diff from a previous DOCX — triggers refine behaviour.
            max_retries: LLM call attempts on validation failure.

        Returns:
            Validated LLMStrategyOutput ready for storage and rendering.

        Raises:
            StrategyGenerationError: All retries exhausted without valid output.
        """
        context = f"{game_name} ({app_id})"
        user = self._build_user_prompt(app_id, game_name, pending, guide, annotations)
        return await self._call_with_retry(
            _STRATEGY_SYSTEM_PROMPT_V1, user, context, max_retries
        )
