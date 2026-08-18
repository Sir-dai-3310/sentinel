"""LLM provider abstraction layer."""

import os
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    async def chat(self, prompt: str, **kwargs: Any) -> str:
        """Send a chat completion request."""
        pass

    @abstractmethod
    async def chat_structured(
        self, prompt: str, output_schema: type[T], **kwargs: Any
    ) -> T:
        """Send a chat completion with structured output."""
        pass

    def is_available(self) -> bool:
        """Check if the provider is available (API key configured)."""
        return True


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(self):
        from langchain_openai import ChatOpenAI

        self.model = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "gpt-4-turbo-preview"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL"),
            max_retries=3,
        )

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        return bool(os.getenv("LLM_API_KEY"))

    async def chat(self, prompt: str, **kwargs: Any) -> str:
        response = await self.model.ainvoke(prompt, **kwargs)
        return response.content

    async def chat_structured(
        self, prompt: str, output_schema: type[T], **kwargs: Any
    ) -> T:
        structured = self.model.with_structured_output(output_schema)
        return await structured.ainvoke(prompt, **kwargs)


class AnthropicProvider(LLMProvider):
    """Anthropic API provider."""

    def __init__(self):
        from langchain_anthropic import ChatAnthropic

        self.model = ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            max_retries=3,
        )

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

    async def chat(self, prompt: str, **kwargs: Any) -> str:
        response = await self.model.ainvoke(prompt, **kwargs)
        return response.content

    async def chat_structured(
        self, prompt: str, output_schema: type[T], **kwargs: Any
    ) -> T:
        structured = self.model.with_structured_output(output_schema)
        return await structured.ainvoke(prompt, **kwargs)


class OllamaProvider(LLMProvider):
    """Ollama local model provider."""

    def __init__(self):
        from langchain_community.chat_models import ChatOllama

        self.model = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        )

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        # Ollama doesn't need API key, just needs the service running
        return True

    async def chat(self, prompt: str, **kwargs: Any) -> str:
        response = await self.model.ainvoke(prompt, **kwargs)
        return response.content

    async def chat_structured(
        self, prompt: str, output_schema: type[T], **kwargs: Any
    ) -> T:
        structured = self.model.with_structured_output(output_schema)
        return await structured.ainvoke(prompt, **kwargs)


class LLMProviderFactory:
    """Factory for creating LLM providers."""

    _providers: dict[str, type[LLMProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
    }

    @classmethod
    def create(cls, provider_name: str | None = None) -> LLMProvider:
        """
        Create an LLM provider.

        Args:
            provider_name: Provider name (openai, anthropic, ollama).
                          If None, reads from LLM_PROVIDER env var.

        Returns:
            LLM provider instance

        Raises:
            ValueError: If provider is not supported
        """
        if provider_name is None:
            provider_name = os.getenv("LLM_PROVIDER", "openai")

        provider_name = provider_name.lower()

        if provider_name not in cls._providers:
            raise ValueError(
                f"Unsupported LLM provider: {provider_name}. "
                f"Supported: {', '.join(cls._providers.keys())}"
            )

        provider_class = cls._providers[provider_name]
        provider = provider_class()

        if not provider.is_available():
            raise ValueError(
                f"Provider {provider_name} is not available. "
                f"Check API key configuration."
            )

        return provider

    @classmethod
    def register(cls, name: str, provider_class: type[LLMProvider]) -> None:
        """Register a custom LLM provider."""
        cls._providers[name] = provider_class

    @classmethod
    def list_providers(cls) -> list[dict[str, Any]]:
        """List all registered providers with availability status."""
        result = []
        for name, provider_class in cls._providers.items():
            try:
                provider = provider_class()
                available = provider.is_available()
            except Exception:
                available = False
            result.append({"name": name, "available": available})
        return result
