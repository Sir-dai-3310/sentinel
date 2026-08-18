"""Preprocessing pipeline tests: mapping, filtering, enrichment, bad config."""

import os

import pytest

from sentinel_agents.preprocessing import (
    DropFilter,
    FieldMapper,
    GeoEnricher,
    Pipeline,
    ThreatIntelEnricher,
    get_pipeline,
    reset_pipeline,
)


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


class TestFieldMapper:
    def test_simple_rename(self):
        m = FieldMapper({"event.id": "EventID"})
        out = m.apply({"EventID": 1})
        assert out["event"]["id"] == 1
        assert out["EventID"] == 1  # original preserved

    def test_nested_source(self):
        m = FieldMapper({"cmd": "process.command_line"})
        out = m.apply({"process": {"command_line": "powershell -enc x"}})
        assert out["cmd"] == "powershell -enc x"

    def test_missing_source_is_noop(self):
        m = FieldMapper({"cmd": "does.not.exist"})
        out = m.apply({"a": 1})
        assert "cmd" not in out

    def test_multiple_mappings(self):
        m = FieldMapper({"id": "EventID", "img": "Image", "cmd": "CommandLine"})
        out = m.apply({"EventID": 1, "Image": "powershell.exe", "CommandLine": "ps"})
        assert (out["id"], out["img"], out["cmd"]) == (1, "powershell.exe", "ps")


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class TestDropFilter:
    def test_matching_rule_drops(self):
        f = DropFilter([{"EventID": 4688, "Image": "svchost.exe"}])
        assert f.apply({"EventID": 4688, "Image": "svchost.exe"}) is None

    def test_partial_match_kept(self):
        f = DropFilter([{"EventID": 4688, "Image": "svchost.exe"}])
        out = f.apply({"EventID": 4688, "Image": "powershell.exe"})
        assert out is not None

    def test_any_of_multiple_rules(self):
        f = DropFilter([{"a": 1}, {"b": 2}])
        assert f.apply({"b": 2, "x": 9}) is None
        assert f.apply({"a": 1}) is None
        assert f.apply({"c": 3}) is not None

    def test_empty_rules_keep_everything(self):
        f = DropFilter([])
        assert f.apply({"a": 1}) == {"a": 1}


# ---------------------------------------------------------------------------
# Geo enrichment
# ---------------------------------------------------------------------------


class TestGeoEnricher:
    def test_known_ip_enriched(self):
        g = GeoEnricher("source.ip", {"203.0.113.10": {"country": "CN"}})
        out = g.apply({"source": {"ip": "203.0.113.10"}})
        assert out["geo"] == {"country": "CN"}

    def test_unknown_ip_untouched(self):
        g = GeoEnricher("source.ip", {"203.0.113.10": {"country": "CN"}})
        out = g.apply({"source": {"ip": "8.8.8.8"}})
        assert "geo" not in out


# ---------------------------------------------------------------------------
# Threat-intel enrichment
# ---------------------------------------------------------------------------


class TestThreatIntelEnricher:
    def test_denylist_hit(self):
        t = ThreatIntelEnricher(denylist=["203.0.113.10"])
        out = t.apply({"SourceIp": "203.0.113.10"})
        assert "203.0.113.10" in out["threat_intel"]["denylist_hits"]

    def test_no_hit_no_field(self):
        t = ThreatIntelEnricher(denylist=["203.0.113.10"])
        out = t.apply({"SourceIp": "8.8.8.8", "msg": "hello"})
        assert "threat_intel" not in out

    def test_failing_hook_skipped_gracefully(self):
        def bad_hook(log):
            raise RuntimeError("intel API down / no creds")

        t = ThreatIntelEnricher(denylist=[], hook=bad_hook)
        out = t.apply({"a": 1})  # must not raise
        assert out == {"a": 1}

    def test_working_hook_merges(self):
        def hook(log):
            return {"score": 42}

        t = ThreatIntelEnricher(denylist=[], hook=hook)
        out = t.apply({"a": 1})
        assert out["threat_intel"]["score"] == 42


# ---------------------------------------------------------------------------
# Pipeline ordering + from_yaml + bad config
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_empty_pipeline_is_identity(self):
        p = Pipeline()
        log = {"a": 1}
        assert p.apply(log) is log

    def test_stages_run_in_order_and_drop_short_circuits(self):
        p = Pipeline([
            FieldMapper({"img": "Image"}),
            DropFilter([{"img": "dropme.exe"}]),
            GeoEnricher("source.ip", {"1.2.3.4": {"country": "XX"}}),
        ])
        # This log gets mapped then dropped by the filter -> None
        assert p.apply({"Image": "dropme.exe"}) is None
        # This one survives and is geo-enriched
        out = p.apply({"Image": "keep.exe", "source": {"ip": "1.2.3.4"}})
        assert out["img"] == "keep.exe"
        assert out["geo"] == {"country": "XX"}

    def test_from_yaml_full_config(self, tmp_path):
        cfg = tmp_path / "pre.yml"
        cfg.write_text(
            """
field_mapping:
  img: Image
filters:
  - img: dropme.exe
enrichment:
  geo:
    ip_field: source.ip
    table:
      "1.2.3.4": {country: "XX"}
  threat_intel:
    denylist: ["1.2.3.4"]
"""
        )
        p = Pipeline.from_yaml(str(cfg))
        # dropped by filter
        assert p.apply({"Image": "dropme.exe"}) is None
        # mapped + geo + denylist
        out = p.apply({"Image": "keep.exe", "source": {"ip": "1.2.3.4"}})
        assert out["img"] == "keep.exe"
        assert out["geo"]["country"] == "XX"
        assert "1.2.3.4" in out["threat_intel"]["denylist_hits"]

    def test_from_yaml_missing_file(self):
        with pytest.raises(FileNotFoundError):
            Pipeline.from_yaml("/nonexistent/pre.yml")

    def test_from_yaml_malformed(self, tmp_path):
        bad = tmp_path / "bad.yml"
        bad.write_text("- this\n- is a list not a mapping\n")
        with pytest.raises(ValueError):
            Pipeline.from_yaml(str(bad))

    def test_from_yaml_bad_field_mapping_type(self, tmp_path):
        bad = tmp_path / "bad2.yml"
        bad.write_text("field_mapping: [not, a, mapping]\n")
        with pytest.raises(ValueError):
            Pipeline.from_yaml(str(bad))


# ---------------------------------------------------------------------------
# Global loader: env override, default, bad config -> no-op
# ---------------------------------------------------------------------------


class TestGetPipeline:
    def setup_method(self):
        reset_pipeline()

    def teardown_method(self):
        reset_pipeline()

    def test_env_override_loads_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "pre.yml"
        cfg.write_text("field_mapping:\n  img: Image\n")
        monkeypatch.setenv("SENTINEL_PREPROCESSING_CONFIG", str(cfg))
        p = get_pipeline()
        assert p.apply({"Image": "x"})["img"] == "x"

    def test_no_config_is_noop(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SENTINEL_PREPROCESSING_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)  # ensure no config/preprocessing.yml
        p = get_pipeline()
        log = {"a": 1}
        assert p.apply(log) is log

    def test_bad_config_falls_back_to_noop(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.yml"
        bad.write_text("- not a mapping\n")
        monkeypatch.setenv("SENTINEL_PREPROCESSING_CONFIG", str(bad))
        p = get_pipeline()  # must not raise
        assert p.apply({"a": 1}) == {"a": 1}
