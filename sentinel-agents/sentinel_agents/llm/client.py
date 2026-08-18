"""LLM client with retry, structured output, and error handling."""

import os
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from sentinel_agents.utils.retry import async_retry

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """
    Wrapper for LLM chat models with:
    - Automatic retry on failure
    - Structured output parsing
    - Token usage tracking
    - Error handling
    """

    def __init__(
        self,
        model: BaseChatModel | None = None,
        temperature: float = 0.2,
        max_retries: int = 3,
    ):
        """
        Initialize LLM client.

        Args:
            model: LangChain chat model (if None, creates ChatOpenAI from env)
            temperature: Sampling temperature
            max_retries: Max retry attempts on failure
        """
        if model is None:
            model = ChatOpenAI(
                model=os.getenv("LLM_MODEL", "gpt-4-turbo-preview"),
                temperature=temperature,
                api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL"),
                max_retries=max_retries,
            )

        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.total_tokens = 0
        self.total_calls = 0

    async def ainvoke(self, prompt: str, **kwargs: Any) -> str:
        """
        Invoke LLM with automatic retry (exponential backoff, retryable
        exceptions only).

        Args:
            prompt: Prompt string
            **kwargs: Additional arguments for the model

        Returns:
            Model response content

        Raises:
            Exception: If all retries fail
        """
        async for attempt in async_retry(attempts=self.max_retries):
            with attempt:
                response = await self.model.ainvoke(prompt, **kwargs)

        self.total_calls += 1

        # Track token usage if available
        if hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
            self.total_tokens += usage.get("total_tokens", 0)

        return response.content

    async def ainvoke_structured(
        self,
        prompt: str,
        output_schema: type[T],
        **kwargs: Any,
    ) -> T:
        """
        Invoke LLM with structured output.

        Args:
            prompt: Prompt string
            output_schema: Pydantic model for output
            **kwargs: Additional arguments

        Returns:
            Parsed output as Pydantic model

        Raises:
            Exception: If parsing fails after retries
        """
        structured_llm = self.model.with_structured_output(output_schema)

        response = await structured_llm.ainvoke(prompt, **kwargs)
        self.total_calls += 1

        return response

    def get_stats(self) -> dict[str, int]:
        """Get usage statistics."""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
        }


# Global default client
_default_client: LLMClient | None = None


def get_default_client() -> LLMClient:
    """Get or create default LLM client."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
