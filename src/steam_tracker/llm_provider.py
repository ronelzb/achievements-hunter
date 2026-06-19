"""Async LLM provider protocol and implementations.

Only the transport layer lives here: the protocol, two provider implementations,
and the factory function.  Prompt building and retry logic belong in
strategy_generator.py.
"""

from __future__ import annotations

from typing import Protocol

from .settings import (
    ANTHROPIC_API_KEY,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
)

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class AsyncLLMProvider(Protocol):
    """Minimal async interface over any LLM provider.

    Callers only see plain text in/out.  Provider-specific errors are
    normalised to ValueError so the retry loop in StrategyGenerator can
    handle them uniformly.
    """

    async def complete(self, system: str, user: str, /) -> str: ...


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


class AsyncAnthropicProvider:
    """Anthropic async Messages API."""

    def __init__(self, api_key: str | None = None) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key or ANTHROPIC_API_KEY or None)

    async def complete(self, system: str, user: str) -> str:
        from anthropic import RateLimitError
        from anthropic.types import TextBlock

        try:
            response = await self._client.messages.create(
                model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except RateLimitError as exc:
            raise ValueError(f"Anthropic rate limit: {exc}") from exc

        block = response.content[0]
        if not isinstance(block, TextBlock):
            raise ValueError(
                f"Expected TextBlock from Anthropic, got {type(block).__name__}"
            )
        return block.text


class AsyncOpenAIProvider:
    """OpenAI async Chat Completions API."""

    def __init__(self, api_key: str | None = None) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key or OPENAI_API_KEY or None)

    async def complete(self, system: str, user: str) -> str:
        from openai import RateLimitError

        try:
            response = await self._client.chat.completions.create(
                model=LLM_MODEL,
                max_completion_tokens=LLM_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except RateLimitError as exc:
            raise ValueError(f"OpenAI rate limit: {exc}") from exc

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("OpenAI returned empty content")
        return content


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def async_provider_from_settings() -> AsyncLLMProvider:
    """Build the async LLM provider from settings.  Fails fast if misconfigured."""
    if not LLM_PROVIDER:
        raise ValueError("LLM_PROVIDER is required in .env (anthropic | openai)")
    if not LLM_MODEL:
        raise ValueError("LLM_MODEL is required in .env")

    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )
        return AsyncAnthropicProvider()

    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return AsyncOpenAIProvider()

    raise ValueError(
        f"Unknown LLM_PROVIDER {LLM_PROVIDER!r}. Supported: 'anthropic', 'openai'."
    )
