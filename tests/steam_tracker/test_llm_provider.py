import pytest

import steam_tracker.llm_provider as llm_module
from steam_tracker.llm_provider import (
    AsyncAnthropicProvider,
    AsyncOpenAIProvider,
    async_provider_from_settings,
)

# ── async_provider_from_settings: validation ─────────────────────────────────


def test_raises_when_llm_provider_missing(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "claude-sonnet-4-6")
    with pytest.raises(ValueError, match="LLM_PROVIDER is required"):
        async_provider_from_settings()


def test_raises_when_llm_model_missing(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "")
    with pytest.raises(ValueError, match="LLM_MODEL is required"):
        async_provider_from_settings()


def test_raises_anthropic_without_api_key(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr(llm_module, "ANTHROPIC_API_KEY", "")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is required"):
        async_provider_from_settings()


def test_raises_openai_without_api_key(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(llm_module, "OPENAI_API_KEY", "")
    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        async_provider_from_settings()


def test_raises_on_unknown_provider(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "gemini-pro")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        async_provider_from_settings()


# ── async_provider_from_settings: correct type returned ──────────────────────


def test_returns_anthropic_provider(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr(llm_module, "ANTHROPIC_API_KEY", "sk-ant-test")
    assert isinstance(async_provider_from_settings(), AsyncAnthropicProvider)


def test_returns_openai_provider(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(llm_module, "OPENAI_API_KEY", "sk-openai-test")
    assert isinstance(async_provider_from_settings(), AsyncOpenAIProvider)


# ── only the chosen provider's key is required ────────────────────────────────


def test_anthropic_does_not_require_openai_key(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr(llm_module, "ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(llm_module, "OPENAI_API_KEY", "")
    assert isinstance(async_provider_from_settings(), AsyncAnthropicProvider)


def test_openai_does_not_require_anthropic_key(monkeypatch):
    monkeypatch.setattr(llm_module, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_module, "LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(llm_module, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(llm_module, "OPENAI_API_KEY", "sk-openai-test")
    assert isinstance(async_provider_from_settings(), AsyncOpenAIProvider)
