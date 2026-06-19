"""Parser hierarchy for steam_tracker."""

import html
import re
from abc import ABC, abstractmethod
from typing import Any

import vdf


class Parser[T](ABC):
    """Root ABC for the parser hierarchy.

    Every parser takes some input and produces a typed output T.
    Subclasses specialise the input type:
      BytesParser — source is raw bytes.
    """

    @abstractmethod
    def parse(self, source: Any) -> T:
        """Parse *source* and return a typed output."""


class InMemoryParser[T](Parser[T], ABC):
    """Strategy interface for parsers that operate on in-memory string content.

    Use when the source is already decoded text rather than a file path or bytes.
    """

    @abstractmethod
    def parse(self, source: str) -> T:
        """Parse *source* string and return a typed output."""


class BytesParser[T](Parser[T], ABC):
    """Strategy interface for parsers that operate on raw bytes.

    Use when the source is binary content rather than a file path or decoded
    string.
    """

    @abstractmethod
    def parse(self, source: bytes) -> T:
        """Parse *source* bytes and return a typed output."""


class HtmlParser(InMemoryParser[str]):
    """Strips HTML tags and normalises whitespace to produce plain text.

    Used to clean scraped web pages.
    """

    def parse(self, source: str) -> str:
        text = re.sub(
            r"<(script|style)[^>]*>.*?</(script|style)>",
            " ",
            source,
            flags=re.DOTALL | re.IGNORECASE,
        )
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class SteamAchievementSchemaParser(BytesParser[dict[str, str]]):
    """Parses a UserGameStatsSchema_APPID.bin file into {api_name: description}.

    The .bin file is binary VDF cached by the Steam client at
    Steam/appcache/stats/. It contains the full achievement schema including
    descriptions for hidden achievements — which GetSchemaForGame intentionally
    omits for games that hide their descriptions at the API level.

    Returns {} on any parse failure so callers can treat this as a best-effort
    supplementary source and fall through gracefully.
    """

    def parse(self, source: bytes) -> dict[str, str]:
        """Return {api_name: english_description} extracted from binary VDF bytes."""
        if not source:
            return {}
        try:
            data = vdf.binary_loads(source)
        except Exception:
            return {}

        stats = self._find_stats(data)
        if not stats:
            return {}

        result: dict[str, str] = {}
        for stat in stats.values():
            if not isinstance(stat, dict):
                continue
            # Some games (e.g. Elden Ring) wrap each achievement under a 'bits'
            # sub-dict; others store achievements flat at this level.
            if "bits" in stat and isinstance(stat["bits"], dict):
                ach_entries = stat["bits"].values()
            else:
                ach_entries = [stat]

            for ach in ach_entries:
                if not isinstance(ach, dict):
                    continue
                api_name = ach.get("name", "")
                if not api_name:
                    continue
                desc = ach.get("display", {}).get("desc", {}).get("english", "")
                if desc:
                    result[str(api_name)] = str(desc)
        return result

    @staticmethod
    def _find_stats(data: dict) -> dict | None:
        """Navigate to the 'stats' dict regardless of top-level app-id wrapper."""
        if "stats" in data:
            return data["stats"]
        for val in data.values():
            if isinstance(val, dict) and "stats" in val:
                return val["stats"]
        return None
