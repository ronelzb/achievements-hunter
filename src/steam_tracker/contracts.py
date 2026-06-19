from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pipeline inputs
# ---------------------------------------------------------------------------

AchievementCategory = Literal[
    "missable", "story", "grind", "collectible", "difficulty", "misc"
]


class PendingAchievement(BaseModel):
    api_name: str
    display_name: str
    description: str  # empty string if hidden and no local cache hit
    is_hidden: bool
    schema_idx: int
    icon_url: str  # Steam CDN URL; empty string if unavailable


class GuideContent(BaseModel):
    source: str  # URL or descriptive label
    raw_text: str  # plain text, capped at 60 000 chars


# ---------------------------------------------------------------------------
# LLM structured output
# ---------------------------------------------------------------------------


class StrategyItem(BaseModel):
    api_name: str
    display_name: str
    tip: str
    guide_link: str = ""  # TrueSteamAchievements URL when confidently known


class StrategySection(BaseModel):
    title: str
    category: AchievementCategory
    overview: str  # 1-2 sentence intro for this section
    items: list[StrategyItem]


class LLMStrategyOutput(BaseModel):
    total_runs: int = Field(..., ge=1)
    estimated_hours: str  # e.g. "25-40"
    summary: str
    sections: list[StrategySection]
    recommended_order: list[str]


# ---------------------------------------------------------------------------
# Refine input
# ---------------------------------------------------------------------------


class UserAnnotations(BaseModel):
    """Delta between the DB-stored baseline strategy and the user-edited DOCX.

    All three diff directions are meaningful:
      added    → new notes, questions, corrections the user wrote
      modified → existing tips the user rephrased or corrected
      deleted  → intentional removals; signals completed, skipped, or inapplicable content
    """

    docx_path: str
    added_lines: list[str]
    modified_lines: list[str]
    deleted_lines: list[str]


# ---------------------------------------------------------------------------
# Pipeline output
# ---------------------------------------------------------------------------


class StrategyResult(BaseModel):
    app_id: int
    game_name: str
    model: str
    output: LLMStrategyOutput
    created_at: datetime
    is_refinement: bool = False
