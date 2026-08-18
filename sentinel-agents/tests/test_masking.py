"""Data masking tests: strategies, nested paths, config, pass-through."""

import pytest

from sentinel_agents.utils.masking import Masker, get_masker, reset_masker


class TestStrategies:
    def test_redact(self):
        m = Masker([{"path": "user.name", "strategy": "redact"}])
        out = m.mask({"user": {"name": "alice"}})
        assert out["user"]["name"] == "***"

    def test_hash_is_stable_and_truncated(self):
        m = Masker([{"path": "user.email", "strategy": "hash"}])
        out1 = m.mask({"user": {"email": "a@b.com"}})
        out2 = m.mask({"user": {"email": "a@b.com"}})
        assert out1["user"]["email"] == out2["user"]["email"]  # stable
        assert len(out1["user"]["email"]) == 16               # truncated
        assert out1["user"]["email"] != "a@b.com"             # not plaintext

    def test_partial_ipv4_keeps_two_octets(self):
        m = Masker([{"path": "source.ip", "strategy": "partial"}])
        out = m.mask({"source": {"ip": "192.168.10.55"}})
        assert out["source"]["ip"] == "192.168.***.***"

    def test_partial_generic_keeps_prefix(self):
        m = Masker([{"path": "process.command_line", "strategy": "partial"}])
        out = m.mask({"process": {"command_line": "powershell -enc SECRET"}})
        assert out["process"]["command_line"] == "pow***"

    def test_unknown_strategy_falls_back_to_redact(self):
        m = Masker([{"path": "a", "strategy": "bogus"}])
        assert m.mask({"a": "secret"})["a"] == "***"


class TestNestedAndEdge:
    def test_multiple_rules(self):
        m = Masker([
            {"path": "user.name", "strategy": "redact"},
            {"path": "source.ip", "strategy": "partial"},
        ])
        out = m.mask({"user": {"name": "bob"}, "source": {"ip": "10.0.0.1"}})
        assert out["user"]["name"] == "***"
        assert out["source"]["ip"] == "10.0.***.***"

    def test_missing_path_is_noop(self):
        m = Masker([{"path": "no.such.path", "strategy": "redact"}])
        payload = {"a": 1}
        assert m.mask(payload) == payload

    def test_does_not_mutate_input(self):
        m = Masker([{"path": "user.name", "strategy": "redact"}])
        payload = {"user": {"name": "carol"}}
        m.mask(payload)
        assert payload["user"]["name"] == "carol"  # original untouched

    def test_top_level_sysmon_field(self):
        m = Masker([{"path": "SourceIp", "strategy": "partial"}])
        out = m.mask({"SourceIp": "172.16.5.5"})
        assert out["SourceIp"] == "172.16.***.***"


class TestDisabled:
    def test_disabled_is_passthrough(self):
        m = Masker([{"path": "user.name", "strategy": "redact"}], enabled=False)
        payload = {"user": {"name": "dave"}}
        assert m.mask(payload) is payload  # same object, zero overhead

    def test_no_rules_is_passthrough(self):
        m = Masker([], enabled=True)
        payload = {"user": {"name": "dave"}}
        assert m.mask(payload) is payload


class TestFromYaml:
    def test_loads_rules(self, tmp_path):
        cfg = tmp_path / "masking.yml"
        cfg.write_text(
            "enabled: true\nrules:\n  - {path: user.name, strategy: redact}\n"
        )
        m = Masker.from_yaml(str(cfg))
        assert m.enabled is True
        assert m.mask({"user": {"name": "x"}})["user"]["name"] == "***"

    def test_env_override_disables(self, tmp_path, monkeypatch):
        cfg = tmp_path / "masking.yml"
        cfg.write_text(
            "enabled: true\nrules:\n  - {path: user.name, strategy: redact}\n"
        )
        monkeypatch.setenv("MASKING_ENABLED", "false")
        m = Masker.from_yaml(str(cfg))
        assert m.enabled is False

    def test_malformed_raises(self, tmp_path):
        bad = tmp_path / "bad.yml"
        bad.write_text("- a list\n")
        with pytest.raises(ValueError):
            Masker.from_yaml(str(bad))


class TestGetMasker:
    def setup_method(self):
        reset_masker()

    def teardown_method(self):
        reset_masker()

    def test_default_disabled(self, monkeypatch):
        monkeypatch.delenv("MASKING_ENABLED", raising=False)
        assert get_masker().enabled is False

    def test_enabled_with_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "masking.yml"
        cfg.write_text("rules:\n  - {path: user.name, strategy: redact}\n")
        monkeypatch.setenv("MASKING_ENABLED", "true")
        monkeypatch.setenv("SENTINEL_MASKING_CONFIG", str(cfg))
        masker = get_masker()
        assert masker.enabled is True
        assert masker.mask({"user": {"name": "x"}})["user"]["name"] == "***"

    def test_bad_config_disables_safely(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.yml"
        bad.write_text("- not a mapping\n")
        monkeypatch.setenv("MASKING_ENABLED", "true")
        monkeypatch.setenv("SENTINEL_MASKING_CONFIG", str(bad))
        assert get_masker().enabled is False  # no raise, pass-through
