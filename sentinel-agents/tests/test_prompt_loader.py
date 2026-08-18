"""Prompt-template externalisation tests: loader override/fallback/bad file."""

import pytest

from sentinel_agents.llm import prompts
from sentinel_agents.llm.prompt_loader import (
    DEFAULT_TEMPLATES,
    load_template,
    template_version,
)


class TestBundledDefault:
    def test_loads_bundled_analysis(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_PROMPTS_DIR", raising=False)
        t = load_template("analysis")
        assert "security analyst AI" in t
        assert "{log}" in t
        # header comment stripped
        assert not t.lstrip().startswith("<!--")

    def test_header_not_in_output(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_PROMPTS_DIR", raising=False)
        assert "version:" not in load_template("hunting").splitlines()[0]


class TestOverride:
    def test_env_dir_overrides(self, tmp_path, monkeypatch):
        (tmp_path / "analysis.md").write_text(
            "<!-- prompt: analysis version: 9.9.9 -->\nCUSTOM OVERRIDE {log}\n"
        )
        monkeypatch.setenv("SENTINEL_PROMPTS_DIR", str(tmp_path))
        t = load_template("analysis")
        assert "CUSTOM OVERRIDE" in t
        assert "security analyst AI" not in t

    def test_override_only_affects_present_files(self, tmp_path, monkeypatch):
        # Only analysis overridden; hunting still falls back to bundled.
        (tmp_path / "analysis.md").write_text("OVERRIDE {log}\n")
        monkeypatch.setenv("SENTINEL_PROMPTS_DIR", str(tmp_path))
        assert "OVERRIDE" in load_template("analysis")
        assert "threat hunting queries" in load_template("hunting")


class TestFallback:
    def test_missing_file_falls_back_to_builtin(self, tmp_path, monkeypatch):
        # Override dir exists but has no analysis.md, and bundled is bypassed
        # by pointing the loader's bundled dir at an empty path.
        import sentinel_agents.llm.prompt_loader as loader

        monkeypatch.setenv("SENTINEL_PROMPTS_DIR", str(tmp_path))  # empty dir
        monkeypatch.setattr(loader, "_BUNDLED_DIR", tmp_path / "nope")
        assert load_template("analysis") == DEFAULT_TEMPLATES["analysis"]

    def test_corrupt_file_falls_back(self, tmp_path, monkeypatch):
        import sentinel_agents.llm.prompt_loader as loader

        bad = tmp_path / "report.md"
        bad.write_bytes(b"\xff\xfe invalid utf-8 \x00")
        monkeypatch.setenv("SENTINEL_PROMPTS_DIR", str(tmp_path))
        monkeypatch.setattr(loader, "_BUNDLED_DIR", tmp_path / "nope")
        assert load_template("report") == DEFAULT_TEMPLATES["report"]

    def test_unknown_template_returns_empty(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_PROMPTS_DIR", raising=False)
        assert load_template("nonexistent-template") == ""


class TestVersion:
    def test_parses_version_header(self):
        text = "<!-- prompt: analysis version: 1.2.3 -->\nbody\n"
        assert template_version(text) == "1.2.3"

    def test_no_version_returns_none(self):
        assert template_version("no header here\n") is None

    def test_bundled_templates_have_versions(self, monkeypatch):
        import sentinel_agents.llm.prompt_loader as loader

        monkeypatch.delenv("SENTINEL_PROMPTS_DIR", raising=False)
        for name in ("analysis", "hunting", "report"):
            raw = (loader._BUNDLED_DIR / f"{name}.md").read_text()
            assert template_version(raw) is not None


class TestBuildersUseTemplates:
    def test_analysis_prompt_format(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_PROMPTS_DIR", raising=False)
        out = prompts.build_analysis_prompt({"EventID": 1, "Image": "powershell.exe"})
        assert "EventID: 1" in out
        assert "security analyst AI" in out

    def test_analysis_prompt_with_context(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_PROMPTS_DIR", raising=False)
        out = prompts.build_analysis_prompt({"a": 1}, context="rule hit R001")
        assert "Additional Context" in out
        assert "rule hit R001" in out

    def test_custom_template_used_by_builder(self, tmp_path, monkeypatch):
        (tmp_path / "analysis.md").write_text("CUSTOM {log} CTX:{context_block}\n")
        monkeypatch.setenv("SENTINEL_PROMPTS_DIR", str(tmp_path))
        out = prompts.build_analysis_prompt({"x": 1})
        assert out.startswith("CUSTOM")

    def test_hunting_and_report(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_PROMPTS_DIR", raising=False)
        assert "threat hunting" in prompts.build_hunting_prompt({"malicious": True})
        assert "incident report" in prompts.build_report_prompt({"verdict": "x"})
