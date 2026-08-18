"""Tests for PDF report generation."""

import os
import tempfile

import pytest

from sentinel_agents.report import ReportGenerator
from sentinel_agents.state import IncidentState, RuleHit, Verdict


@pytest.fixture
def sample_state():
    """Create a sample incident state."""
    state = IncidentState(log={"EventID": 1, "Image": "powershell.exe", "CommandLine": "powershell -enc test"})
    state.verdict = Verdict(
        malicious=True,
        danger_level=85,
        reason="PowerShell encoded command detected",
        mitre_techniques=["T1059.001", "T1027"],
        recommended_actions=["Isolate host", "Collect memory dump", "Analyze network traffic"],
    )
    state.rule_hits = [
        RuleHit(
            rule_id="R001",
            rule_name="PowerShell Encoded Command",
            technique="T1059.001",
            confidence=85,
            severity="high",
            reason="Encoded PowerShell command",
        ),
        RuleHit(
            rule_id="R005",
            rule_name="Hidden Window",
            technique="T1564.003",
            confidence=80,
            severity="medium",
            reason="Hidden window execution",
        ),
    ]
    state.agent_trace = ["TriageAgent", "AnalystAgent", "HunterAgent", "ReporterAgent"]
    return state


@pytest.fixture
def benign_state():
    """Create a benign incident state."""
    state = IncidentState(log={"EventID": 1, "Image": "chrome.exe"})
    state.verdict = Verdict(
        malicious=False,
        danger_level=5,
        reason="No malicious indicators found",
        mitre_techniques=[],
        recommended_actions=["Continue monitoring"],
    )
    state.rule_hits = []
    state.agent_trace = ["TriageAgent"]
    return state


class TestReportGenerator:
    """Tests for ReportGenerator."""

    def test_generate_creates_file(self, sample_state):
        """Test that generate creates a PDF file."""
        gen = ReportGenerator()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            result = gen.generate(sample_state, path)
            assert result == path
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)

    def test_generate_content_malicious(self, sample_state):
        """Test that generated PDF contains expected content for malicious verdict."""
        gen = ReportGenerator()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            gen.generate(sample_state, path)

            # Extract text and verify content
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""

            # Verify key sections exist. Rule names wrap inside Paragraph
            # cells and adjacent cells (R001) render between the wrapped
            # lines in extraction order, so match the name in two parts.
            # (Contiguous per-column verification lives in
            #  test_report_content.py using word x-coordinates.)
            assert "Sentinel Security Analysis Report" in text
            assert "MALICIOUS" in text
            assert "85/100" in text
            assert "PowerShell encoded command detected" in text
            assert "T1059.001" in text
            assert "T1027" in text
            assert "PowerShell Encoded" in text
            assert "Command" in text
            assert "Hidden Window" in text
            assert "TriageAgent" in text
            assert "AnalystAgent" in text
            assert "Isolate host" in text
            assert "Collect memory dump" in text
        finally:
            os.unlink(path)

    def test_generate_content_benign(self, benign_state):
        """Test that generated PDF contains expected content for benign verdict."""
        gen = ReportGenerator()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            gen.generate(benign_state, path)

            import pdfplumber
            with pdfplumber.open(path) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""

            assert "Sentinel Security Analysis Report" in text
            assert "BENIGN" in text
            assert "5/100" in text
            assert "No malicious indicators found" in text
            assert "TriageAgent" in text
        finally:
            os.unlink(path)

    def test_generate_empty_state(self):
        """Test report generation with minimal state."""
        gen = ReportGenerator()
        state = IncidentState(log={})

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            gen.generate(state, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)

    def test_generate_bytes(self, sample_state):
        """Test PDF generation as bytes."""
        gen = ReportGenerator()
        content = gen.generate_bytes(sample_state)
        assert isinstance(content, bytes)
        assert len(content) > 0
        # PDF files start with %PDF
        assert content[:4] == b"%PDF"
