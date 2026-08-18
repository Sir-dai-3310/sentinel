"""Content-level verification of generated PDF reports using pdfplumber.

Unlike test_report.py (which checks file existence / magic bytes), these
tests extract the actual text layer of the PDF and assert every expected
section and field is present, plus failure scenarios.
"""

import os

import pdfplumber
import pytest

from sentinel_agents.report import ReportGenerator
from sentinel_agents.state import IncidentState, RuleHit, Verdict


def _extract_text(pdf_path: str) -> str:
    """Extract full text from a PDF file."""
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _normalize(text: str) -> str:
    """Collapse all whitespace so wrapped table cells match."""
    return " ".join(text.split())


def _extract_tables(pdf_path: str) -> list[list[list[str]]]:
    """Extract structured tables from a PDF (row-major, cell text)."""
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                tables.append(table)
    return tables


# Table geometry from ReportGenerator.
# SimpleDocTemplate centers the table horizontally on letter paper:
#   page_width = 612pt, margins 72pt -> usable 468pt
#   table_width = (1.0+1.8+1+0.8+0.8) inches = 388.8pt
#   left edge = 72 + (468-388.8)/2 = 111.6pt
_INCH = 72
_TABLE_LEFT = 111.6
_COL_X = {
    "rule_id": (_TABLE_LEFT, _TABLE_LEFT + 1.0 * _INCH),
    "name": (_TABLE_LEFT + 1.0 * _INCH, _TABLE_LEFT + 2.8 * _INCH),
    "technique": (_TABLE_LEFT + 2.8 * _INCH, _TABLE_LEFT + 3.8 * _INCH),
    "confidence": (_TABLE_LEFT + 3.8 * _INCH, _TABLE_LEFT + 4.6 * _INCH),
    "severity": (_TABLE_LEFT + 4.6 * _INCH, _TABLE_LEFT + 5.4 * _INCH),
}


def _column_text(pdf_path: str, column: str) -> str:
    """Reconstruct a table column's text from word x-positions.

    pdfplumber's extract_text() interleaves wrapped cells line-by-line
    (e.g. 'TC1o0m59m.0a0n1d'), so we filter words by x-range instead.
    """
    x0, x1 = _COL_X[column]
    words = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for w in page.extract_words():
                if x0 <= w["x0"] < x1:
                    words.append((w["top"], w["x0"], w["text"]))
    # Reading order: top-to-bottom, then left-to-right
    words.sort(key=lambda t: (round(t[0], 1), t[1]))
    return " ".join(w[2] for w in words)


def _pdf_page_count(pdf_path: str) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


@pytest.fixture
def malicious_state() -> IncidentState:
    return IncidentState(
        log={
            "EventID": 4688,
            "Image": "powershell.exe",
            "CommandLine": "powershell -enc SQBFAFgA...",
            "User": "DESKTOP-01\\admin",
        },
        rule_hits=[
            RuleHit(
                rule_id="sigma-ps-001",
                rule_name="Suspicious PowerShell Encoded Command",
                technique="T1059.001",
                confidence=95,
                severity="high",
                reason="Encoded command line detected",
            ),
            RuleHit(
                rule_id="sigma-ps-002",
                rule_name="PowerShell Download Cradle",
                technique="T1105",
                confidence=80,
                severity="medium",
                reason="Download pattern",
            ),
        ],
        verdict=Verdict(
            malicious=True,
            danger_level=92,
            reason="Encoded PowerShell command with download cradle pattern",
            mitre_techniques=["T1059.001", "T1105"],
            recommended_actions=[
                "Isolate host DESKTOP-01 immediately",
                "Reset credentials for user admin",
                "Block the destination IP at the perimeter",
            ],
        ),
        agent_trace=["TriageAgent", "AnalystAgent", "HunterAgent", "ReporterAgent"],
    )


@pytest.fixture
def benign_state() -> IncidentState:
    return IncidentState(
        log={"EventID": 4624, "Image": "svchost.exe", "User": "SYSTEM"},
        rule_hits=[],
        verdict=Verdict(
            malicious=False,
            danger_level=5,
            reason="Normal system process activity",
            mitre_techniques=[],
            recommended_actions=["No action required"],
        ),
        agent_trace=["TriageAgent", "ReporterAgent"],
    )


class TestPDFContentVerification:
    """Extract PDF text and assert every section is present."""

    def test_malicious_report_full_content(self, malicious_state, tmp_path):
        out = str(tmp_path / "report.pdf")
        gen = ReportGenerator()
        gen.generate(malicious_state, out)

        assert os.path.getsize(out) > 1000, "PDF suspiciously small"
        text = _extract_text(out)

        # Title and metadata
        assert "Sentinel Security Analysis Report" in text
        assert "Generated:" in text

        # Executive summary
        assert "Executive Summary" in text
        assert "MALICIOUS" in text
        assert "92/100" in text
        assert "Encoded PowerShell command with download cradle pattern" in text

        # MITRE techniques
        assert "MITRE ATT" in text  # "MITRE ATT&CK Techniques" (& may extract oddly)
        assert "T1059.001" in text
        assert "T1105" in text

        # Rule hits table: raw text extraction interleaves wrapped cells
        # line-by-line, so verify each column via word x-coordinate ranges
        assert "Rule Hits" in text
        rule_id_col = _column_text(out, "rule_id")
        name_col = _column_text(out, "name")
        technique_col = _column_text(out, "technique")
        severity_col = _column_text(out, "severity")

        # Column headers actually rendered
        assert "Rule ID" in rule_id_col
        assert "Name" in name_col
        assert "Technique" in technique_col
        assert "Severity" in severity_col

        # Both rule rows present, cells reassembled correctly per column
        assert "sigma-ps-001" in rule_id_col
        assert "sigma-ps-002" in rule_id_col
        assert "Suspicious PowerShell Encoded Command" in name_col
        assert "PowerShell Download Cradle" in name_col
        assert "T1105" in technique_col
        assert "high" in severity_col
        assert "medium" in severity_col

        # Agent trace
        assert "Agent Execution Trace" in text
        assert "TriageAgent" in text
        assert "ReporterAgent" in text

        # Recommended actions
        assert "Recommended Actions" in text
        assert "Isolate host DESKTOP-01 immediately" in text
        assert "Reset credentials for user admin" in text

        # Log event section
        assert "Log Event" in text
        assert "powershell.exe" in text

    def test_benign_report_content(self, benign_state, tmp_path):
        out = str(tmp_path / "benign.pdf")
        ReportGenerator().generate(benign_state, out)
        text = _extract_text(out)

        assert "BENIGN" in text
        assert "5/100" in text
        assert "Normal system process activity" in text
        assert "No action required" in text
        # No rule hits -> no rule table header
        assert "Rule ID" not in text

    def test_report_page_count_reasonable(self, malicious_state, tmp_path):
        out = str(tmp_path / "p.pdf")
        ReportGenerator().generate(malicious_state, out)
        pages = _pdf_page_count(out)
        assert 1 <= pages <= 5, f"Unexpected page count: {pages}"

    def test_long_log_truncated(self, tmp_path):
        """Logs longer than 500 chars are truncated with ellipsis."""
        state = IncidentState(
            log={"data": "A" * 2000},
            verdict=Verdict(malicious=False, danger_level=0, reason="test"),
        )
        out = str(tmp_path / "long.pdf")
        ReportGenerator().generate(state, out)
        text = _extract_text(out)
        assert "..." in text
        # The full 2000-char payload must NOT appear
        assert "A" * 2000 not in text

    def test_empty_state_minimal_report(self, tmp_path):
        """State with no verdict/hits still produces a valid PDF."""
        state = IncidentState(log={"EventID": 1})
        out = str(tmp_path / "empty.pdf")
        ReportGenerator().generate(state, out)
        text = _extract_text(out)
        assert "Sentinel Security Analysis Report" in text
        assert "Log Event" in text
        # No verdict -> no status line
        assert "MALICIOUS" not in text
        assert "BENIGN" not in text

    def test_generate_bytes_returns_valid_pdf(self, malicious_state):
        content = ReportGenerator().generate_bytes(malicious_state)
        assert isinstance(content, bytes)
        assert content[:5] == b"%PDF-"
        assert len(content) > 1000

        # Verify bytes are a parseable PDF with content
        import io

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        assert "Sentinel Security Analysis Report" in text
        assert "sigma-ps-001" in text

    def test_generate_to_invalid_path_raises(self, malicious_state):
        """Writing to a nonexistent directory must raise, not silently pass."""
        gen = ReportGenerator()
        with pytest.raises(Exception):
            gen.generate(malicious_state, "/nonexistent-dir-xyz/report.pdf")

    def test_unicode_log_content(self, tmp_path):
        """Non-ASCII log data must not crash report generation."""
        state = IncidentState(
            log={"User": "用户名", "Path": "C:\\用户\\文件.exe"},
            verdict=Verdict(malicious=False, danger_level=1, reason="unicode test"),
        )
        out = str(tmp_path / "unicode.pdf")
        result = ReportGenerator().generate(state, out)
        assert os.path.exists(result)
        assert os.path.getsize(out) > 500


class TestPDFFieldCompleteness:
    """Field-by-field assertions so a missing section fails loudly."""

    REQUIRED_MALICIOUS_FIELDS = [
        "Sentinel Security Analysis Report",
        "Executive Summary",
        "Status",
        "Danger Level",
        "Reason",
        "MITRE ATT",
        "Rule Hits",
        "Agent Execution Trace",
        "Recommended Actions",
        "Log Event",
    ]

    def test_all_sections_present(self, malicious_state, tmp_path):
        out = str(tmp_path / "full.pdf")
        ReportGenerator().generate(malicious_state, out)
        text = _extract_text(out)
        missing = [f for f in self.REQUIRED_MALICIOUS_FIELDS if f not in text]
        assert not missing, f"PDF missing sections: {missing}"
