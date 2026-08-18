"""Tests for LLM provider abstraction layer and cost tracking."""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from sentinel_agents.llm.cost_tracker import (
    MODEL_PRICING,
    CostTracker,
    TokenUsage,
    get_cost_tracker,
)
from sentinel_agents.llm.providers import (
    LLMProvider,
    LLMProviderFactory,
    OpenAIProvider,
)


class DummyOutput(BaseModel):
    """Schema for structured output tests."""

    verdict: str
    confidence: float


# ---------------------------------------------------------------------------
# Cost tracker
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_defaults(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.model == ""
        assert usage.timestamp > 0

    def test_custom_values(self):
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15, model="gpt-4o")
        assert usage.prompt_tokens == 10
        assert usage.model == "gpt-4o"


class TestCostTracker:
    def test_record_single_known_model(self):
        tracker = CostTracker()
        tracker.record(
            TokenUsage(
                prompt_tokens=1000,
                completion_tokens=1000,
                total_tokens=2000,
                model="gpt-4o",
            )
        )
        summary = tracker.get_summary()
        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 2000
        assert summary["total_prompt_tokens"] == 1000
        assert summary["total_completion_tokens"] == 1000
        # gpt-4o: 0.005/1K prompt + 0.015/1K completion = 0.02
        assert summary["estimated_cost_usd"] == pytest.approx(0.02, abs=1e-4)
        assert summary["calls_by_model"] == {"gpt-4o": 1}
        assert summary["tokens_by_model"] == {"gpt-4o": 2000}

    def test_record_unknown_model_zero_cost(self):
        tracker = CostTracker()
        tracker.record(
            TokenUsage(prompt_tokens=500, completion_tokens=500, total_tokens=1000, model="some-new-model")
        )
        summary = tracker.get_summary()
        assert summary["total_calls"] == 1
        assert summary["estimated_cost_usd"] == 0.0
        assert summary["calls_by_model"] == {"some-new-model": 1}

    def test_record_empty_model_name(self):
        tracker = CostTracker()
        tracker.record(TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2))
        summary = tracker.get_summary()
        assert summary["calls_by_model"] == {"unknown": 1}

    def test_record_multiple_models_aggregation(self):
        tracker = CostTracker()
        tracker.record(TokenUsage(100, 50, 150, "gpt-4o-mini"))
        tracker.record(TokenUsage(200, 100, 300, "gpt-4o-mini"))
        tracker.record(TokenUsage(10, 10, 20, "llama3"))
        summary = tracker.get_summary()
        assert summary["total_calls"] == 3
        assert summary["total_tokens"] == 470
        assert summary["calls_by_model"]["gpt-4o-mini"] == 2
        assert summary["calls_by_model"]["llama3"] == 1
        assert summary["tokens_by_model"]["gpt-4o-mini"] == 450
        # llama3 is free
        # gpt-4o-mini: (300/1000)*0.00015 + (150/1000)*0.0006 = 0.000135
        # summary rounds to 4 decimals -> 0.0001
        assert summary["estimated_cost_usd"] == pytest.approx(0.0001, abs=1e-6)

    def test_free_local_model(self):
        tracker = CostTracker()
        tracker.record(TokenUsage(10000, 10000, 20000, "llama3"))
        assert tracker.get_summary()["estimated_cost_usd"] == 0.0

    def test_reset(self):
        tracker = CostTracker()
        tracker.record(TokenUsage(100, 100, 200, "gpt-4"))
        tracker.reset()
        summary = tracker.get_summary()
        assert summary["total_calls"] == 0
        assert summary["total_tokens"] == 0
        assert summary["estimated_cost_usd"] == 0.0
        assert summary["calls_by_model"] == {}

    def test_all_priced_models_have_valid_structure(self):
        for model, pricing in MODEL_PRICING.items():
            assert "prompt" in pricing
            assert "completion" in pricing
            assert pricing["prompt"] >= 0
            assert pricing["completion"] >= 0

    def test_global_tracker_singleton(self):
        t1 = get_cost_tracker()
        t2 = get_cost_tracker()
        assert t1 is t2


# ---------------------------------------------------------------------------
# Provider base class
# ---------------------------------------------------------------------------


class TestLLMProviderBase:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_default_is_available_true(self):
        class MinimalProvider(LLMProvider):
            @property
            def name(self) -> str:
                return "minimal"

            async def chat(self, prompt: str, **kwargs):
                return "ok"

            async def chat_structured(self, prompt, output_schema, **kwargs):
                return output_schema(verdict="benign", confidence=0.1)

        provider = MinimalProvider()
        assert provider.is_available() is True
        assert provider.name == "minimal"


# ---------------------------------------------------------------------------
# OpenAI provider (langchain-openai installed in env)
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    def test_name_and_availability(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        provider = OpenAIProvider()
        assert provider.name == "openai"
        assert provider.is_available() is True

    def test_raises_without_key(self, monkeypatch):
        """ChatOpenAI validates its env: constructor raises when no key."""
        import openai

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(openai.OpenAIError):
            OpenAIProvider()

    def test_is_available_reflects_env(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        provider = OpenAIProvider()
        assert provider.is_available() is True
        monkeypatch.delenv("LLM_API_KEY")
        assert provider.is_available() is False

    @pytest.mark.asyncio
    async def test_chat_returns_content(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        provider = OpenAIProvider()
        mock_response = MagicMock()
        mock_response.content = "analysis result"
        mock_ainvoke = AsyncMock(return_value=mock_response)

        with patch.object(type(provider.model), "ainvoke", mock_ainvoke):
            result = await provider.chat("analyze this log")
        assert result == "analysis result"
        mock_ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chat_structured(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        provider = OpenAIProvider()

        expected = DummyOutput(verdict="malicious", confidence=0.95)
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(return_value=expected)
        mock_wso = MagicMock(return_value=mock_structured)

        with patch.object(type(provider.model), "with_structured_output", mock_wso):
            result = await provider.chat_structured("analyze", DummyOutput)
        assert result.verdict == "malicious"
        assert result.confidence == 0.95
        mock_wso.assert_called_once_with(DummyOutput)


# ---------------------------------------------------------------------------
# Anthropic / Ollama providers (packages not installed → stub sys.modules)
# ---------------------------------------------------------------------------


def _install_fake_anthropic_module():
    """Inject a fake langchain_anthropic module so AnthropicProvider imports."""
    fake_mod = types.ModuleType("langchain_anthropic")

    class FakeChatAnthropic:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.ainvoke = AsyncMock()
            self.with_structured_output = MagicMock()

    fake_mod.ChatAnthropic = FakeChatAnthropic
    return fake_mod


def _install_fake_ollama_modules():
    """Inject fake langchain_community.chat_models so OllamaProvider imports."""
    fake_chat = types.ModuleType("langchain_community.chat_models")

    class FakeChatOllama:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.ainvoke = AsyncMock()
            self.with_structured_output = MagicMock()

    fake_chat.ChatOllama = FakeChatOllama
    fake_pkg = types.ModuleType("langchain_community")
    fake_pkg.chat_models = fake_chat
    return fake_pkg, fake_chat


class TestAnthropicProvider:
    def test_provider_with_stubbed_module(self, monkeypatch):
        fake_mod = _install_fake_anthropic_module()
        monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_mod)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        # Force re-import path: import here to use stub
        from sentinel_agents.llm.providers import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.name == "anthropic"
        assert provider.is_available() is True

    def test_unavailable_without_key(self, monkeypatch):
        fake_mod = _install_fake_anthropic_module()
        monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_mod)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from sentinel_agents.llm.providers import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.is_available() is False

    @pytest.mark.asyncio
    async def test_chat(self, monkeypatch):
        fake_mod = _install_fake_anthropic_module()
        monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_mod)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        from sentinel_agents.llm.providers import AnthropicProvider

        provider = AnthropicProvider()
        mock_response = MagicMock()
        mock_response.content = "anthropic says hi"
        provider.model.ainvoke = AsyncMock(return_value=mock_response)

        assert await provider.chat("hello") == "anthropic says hi"

    @pytest.mark.asyncio
    async def test_chat_structured(self, monkeypatch):
        fake_mod = _install_fake_anthropic_module()
        monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_mod)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        from sentinel_agents.llm.providers import AnthropicProvider

        provider = AnthropicProvider()
        expected = DummyOutput(verdict="suspicious", confidence=0.6)
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(return_value=expected)
        provider.model.with_structured_output = MagicMock(return_value=mock_structured)

        result = await provider.chat_structured("go", DummyOutput)
        assert result.verdict == "suspicious"


class TestOllamaProvider:
    def test_provider_with_stubbed_module(self, monkeypatch):
        fake_pkg, fake_chat = _install_fake_ollama_modules()
        monkeypatch.setitem(sys.modules, "langchain_community", fake_pkg)
        monkeypatch.setitem(sys.modules, "langchain_community.chat_models", fake_chat)

        from sentinel_agents.llm.providers import OllamaProvider

        provider = OllamaProvider()
        assert provider.name == "ollama"
        # Ollama needs no API key
        assert provider.is_available() is True

    @pytest.mark.asyncio
    async def test_chat(self, monkeypatch):
        fake_pkg, fake_chat = _install_fake_ollama_modules()
        monkeypatch.setitem(sys.modules, "langchain_community", fake_pkg)
        monkeypatch.setitem(sys.modules, "langchain_community.chat_models", fake_chat)

        from sentinel_agents.llm.providers import OllamaProvider

        provider = OllamaProvider()
        mock_response = MagicMock()
        mock_response.content = "local model output"
        provider.model.ainvoke = AsyncMock(return_value=mock_response)

        assert await provider.chat("test") == "local model output"

    @pytest.mark.asyncio
    async def test_chat_structured(self, monkeypatch):
        fake_pkg, fake_chat = _install_fake_ollama_modules()
        monkeypatch.setitem(sys.modules, "langchain_community", fake_pkg)
        monkeypatch.setitem(sys.modules, "langchain_community.chat_models", fake_chat)

        from sentinel_agents.llm.providers import OllamaProvider

        provider = OllamaProvider()
        expected = DummyOutput(verdict="benign", confidence=0.2)
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(return_value=expected)
        provider.model.with_structured_output = MagicMock(return_value=mock_structured)

        result = await provider.chat_structured("go", DummyOutput)
        assert result.verdict == "benign"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestLLMProviderFactory:
    def test_create_openai_default(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        provider = LLMProviderFactory.create()
        assert isinstance(provider, OpenAIProvider)
        assert provider.name == "openai"

    def test_create_by_name_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        provider = LLMProviderFactory.create("OpenAI")
        assert provider.name == "openai"

    def test_create_from_env_var(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        provider = LLMProviderFactory.create()
        assert provider.name == "openai"

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMProviderFactory.create("nonexistent-llm")

    def test_unavailable_provider_raises(self, monkeypatch):
        """Without API key the provider constructor raises before availability check."""
        import openai

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(openai.OpenAIError):
            LLMProviderFactory.create("openai")

    def test_register_custom_provider(self):
        class CustomProvider(LLMProvider):
            @property
            def name(self):
                return "custom"

            async def chat(self, prompt, **kwargs):
                return "custom"

            async def chat_structured(self, prompt, output_schema, **kwargs):
                return None

        LLMProviderFactory.register("custom-test", CustomProvider)
        try:
            provider = LLMProviderFactory.create("custom-test")
            assert provider.name == "custom"
        finally:
            del LLMProviderFactory._providers["custom-test"]

    def test_list_providers(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        providers = LLMProviderFactory.list_providers()
        names = {p["name"] for p in providers}
        assert "openai" in names
        # Each entry has name + available keys
        for entry in providers:
            assert "name" in entry
            assert "available" in entry
        # openai should be available with the key set
        openai_entry = next(p for p in providers if p["name"] == "openai")
        assert openai_entry["available"] is True

    def test_list_providers_handles_import_errors(self, monkeypatch):
        """Providers whose deps are missing show available=False, not crash."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        # anthropic/ollama packages are not installed in this env;
        # list_providers must swallow the ImportError
        providers = LLMProviderFactory.list_providers()
        assert isinstance(providers, list)
        assert len(providers) >= 3
