"""Per-task LLM config + params passthrough tests."""

import pytest

from sentinel_agents.llm.config import LLMConfig, get_llm_config, reset_llm_config
from sentinel_agents.llm.providers import LLMProviderFactory


@pytest.fixture(autouse=True)
def _reset():
    reset_llm_config()
    yield
    reset_llm_config()


class TestConfigLoad:
    def test_loads_tasks(self, tmp_path):
        cfg = tmp_path / "llm.yml"
        cfg.write_text(
            "default: {provider: openai, model: gpt-4o-mini, temperature: 0.2}\n"
            "tasks:\n"
            "  analyst: {provider: openai, model: gpt-4o, temperature: 0.2, top_p: 0.9}\n"
            "  triage: {provider: ollama, model: llama3, temperature: 0.1}\n"
        )
        c = LLMConfig.from_yaml(str(cfg))
        assert c.for_task("analyst")["model"] == "gpt-4o"
        assert c.for_task("triage")["provider"] == "ollama"

    def test_task_inherits_default(self, tmp_path):
        cfg = tmp_path / "llm.yml"
        cfg.write_text(
            "default: {provider: openai, temperature: 0.2, max_tokens: 1024}\n"
            "tasks:\n  hunter: {model: claude-x}\n"
        )
        c = LLMConfig.from_yaml(str(cfg))
        eff = c.for_task("hunter")
        assert eff["model"] == "claude-x"        # task wins
        assert eff["temperature"] == 0.2         # inherited from default
        assert eff["max_tokens"] == 1024

    def test_unknown_task_returns_default(self, tmp_path):
        cfg = tmp_path / "llm.yml"
        cfg.write_text("default: {provider: openai, model: gpt-4o-mini}\n")
        c = LLMConfig.from_yaml(str(cfg))
        assert c.for_task("no-such-task")["model"] == "gpt-4o-mini"

    def test_missing_file_is_empty_config(self):
        c = LLMConfig.from_yaml("/nonexistent/llm.yml")
        assert c.for_task("analyst") == {}

    def test_malformed_raises(self, tmp_path):
        bad = tmp_path / "bad.yml"
        bad.write_text("- a list not a mapping\n")
        with pytest.raises(ValueError):
            LLMConfig.from_yaml(str(bad))

    def test_env_override_path(self, tmp_path, monkeypatch):
        cfg = tmp_path / "custom.yml"
        cfg.write_text("tasks:\n  triage: {provider: ollama, model: llama3}\n")
        monkeypatch.setenv("SENTINEL_LLM_CONFIG", str(cfg))
        c = get_llm_config()
        assert c.for_task("triage")["provider"] == "ollama"


class TestParamsPassthrough:
    def test_params_for_task(self, tmp_path, monkeypatch):
        cfg = tmp_path / "llm.yml"
        cfg.write_text(
            "tasks:\n"
            "  analyst: {provider: openai, model: gpt-4o, temperature: 0.2, max_tokens: 2048, top_p: 0.9}\n"
        )
        monkeypatch.setenv("SENTINEL_LLM_CONFIG", str(cfg))
        reset_llm_config()
        params = LLMProviderFactory.params_for_task("analyst")
        assert params == {"temperature": 0.2, "max_tokens": 2048, "top_p": 0.9}

    def test_params_empty_when_unconfigured(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_LLM_CONFIG", "/nonexistent/llm.yml")
        reset_llm_config()
        assert LLMProviderFactory.params_for_task("analyst") == {}

    def test_create_for_task_uses_config_provider(self, tmp_path, monkeypatch):
        """The factory must pick the provider named in config for the task.

        Uses a stub provider so the test does not depend on optional
        langchain extras (langchain_community) being installed.
        """
        from sentinel_agents.llm.providers import LLMProvider

        created = {}

        class _StubProvider(LLMProvider):
            def __init__(self, **kwargs):
                created.update(kwargs)

            @property
            def name(self):
                return "stub"

            async def chat(self, prompt, **kwargs):
                return ""

            async def chat_structured(self, prompt, output_schema, **kwargs):
                return None

        cfg = tmp_path / "llm.yml"
        cfg.write_text("tasks:\n  triage: {provider: stub, model: m1}\n")
        monkeypatch.setenv("SENTINEL_LLM_CONFIG", str(cfg))
        reset_llm_config()

        monkeypatch.setitem(LLMProviderFactory._providers, "stub", _StubProvider)
        provider = LLMProviderFactory.create_for_task("triage")
        assert provider.name == "stub"

