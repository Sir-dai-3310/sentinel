"""PDF report generation for Sentinel."""

import os
from datetime import UTC, datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from sentinel_agents.state import IncidentState


class ReportGenerator:
    """Generate PDF reports from analysis results."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles."""
        self.styles.add(
            ParagraphStyle(
                name="Title_Custom",
                parent=self.styles["Title"],
                fontSize=24,
                textColor=colors.HexColor("#1a1a2e"),
                spaceAfter=30,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="Heading_Custom",
                parent=self.styles["Heading2"],
                fontSize=14,
                textColor=colors.HexColor("#16213e"),
                spaceAfter=12,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="Body_Custom",
                parent=self.styles["BodyText"],
                fontSize=10,
                leading=14,
            )
        )

    def generate(self, state: IncidentState, output_path: str) -> str:
        """
        Generate a PDF report from an incident state.

        Args:
            state: Complete incident state
            output_path: Output file path

        Returns:
            Path to generated PDF
        """
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )

        story = []

        # Title
        story.append(Paragraph("Sentinel Security Analysis Report", self.styles["Title_Custom"]))
        story.append(Spacer(1, 12))

        # Metadata
        story.append(
            Paragraph(
                f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                self.styles["Normal"],
            )
        )
        story.append(Spacer(1, 20))

        # Executive Summary
        story.append(Paragraph("Executive Summary", self.styles["Heading_Custom"]))
        verdict = state.verdict
        if verdict:
            status = "MALICIOUS" if verdict.malicious else "BENIGN"
            story.append(
                Paragraph(
                    f"<b>Status:</b> {status}",
                    self.styles["Body_Custom"],
                )
            )
            story.append(
                Paragraph(
                    f"<b>Danger Level:</b> {verdict.danger_level}/100",
                    self.styles["Body_Custom"],
                )
            )
            story.append(
                Paragraph(
                    f"<b>Reason:</b> {verdict.reason}",
                    self.styles["Body_Custom"],
                )
            )
        story.append(Spacer(1, 20))

        # MITRE ATT&CK Techniques
        if verdict and verdict.mitre_techniques:
            story.append(Paragraph("MITRE ATT&CK Techniques", self.styles["Heading_Custom"]))
            for technique in verdict.mitre_techniques:
                story.append(Paragraph(f"• {technique}", self.styles["Body_Custom"]))
            story.append(Spacer(1, 20))

        # Rule Hits
        if state.rule_hits:
            story.append(Paragraph("Rule Hits", self.styles["Heading_Custom"]))
            # Use Paragraph for cell text so ReportLab wraps long content
            # within cell boundaries instead of overflowing into adjacent columns
            cell_style = ParagraphStyle(
                name="Cell",
                parent=self.styles["Normal"],
                fontSize=9,
                leading=11,
            )
            table_data = [
                [
                    Paragraph("<b>Rule ID</b>", cell_style),
                    Paragraph("<b>Name</b>", cell_style),
                    Paragraph("<b>Technique</b>", cell_style),
                    Paragraph("<b>Confidence</b>", cell_style),
                    Paragraph("<b>Severity</b>", cell_style),
                ]
            ]
            for hit in state.rule_hits:
                table_data.append([
                    Paragraph(hit.rule_id, cell_style),
                    Paragraph(hit.rule_name, cell_style),
                    Paragraph(hit.technique, cell_style),
                    Paragraph(str(hit.confidence), cell_style),
                    Paragraph(hit.severity, cell_style),
                ])

            table = Table(table_data, colWidths=[1.0*inch, 1.8*inch, 1*inch, 0.8*inch, 0.8*inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
                ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
            ]))
            story.append(table)
            story.append(Spacer(1, 20))

        # Agent Execution Trace
        if state.agent_trace:
            story.append(Paragraph("Agent Execution Trace", self.styles["Heading_Custom"]))
            trace_text = " → ".join(state.agent_trace)
            story.append(Paragraph(trace_text, self.styles["Body_Custom"]))
            story.append(Spacer(1, 20))

        # Recommended Actions
        if verdict and verdict.recommended_actions:
            story.append(Paragraph("Recommended Actions", self.styles["Heading_Custom"]))
            for i, action in enumerate(verdict.recommended_actions, 1):
                story.append(Paragraph(f"{i}. {action}", self.styles["Body_Custom"]))
            story.append(Spacer(1, 20))

        # Log Event
        story.append(Paragraph("Log Event", self.styles["Heading_Custom"]))
        log_text = str(state.log)
        if len(log_text) > 500:
            log_text = log_text[:500] + "..."
        story.append(Paragraph(log_text, self.styles["Body_Custom"]))

        # Build PDF
        doc.build(story)
        return output_path

    def generate_bytes(self, state: IncidentState) -> bytes:
        """
        Generate PDF report as bytes.

        Args:
            state: Complete incident state

        Returns:
            PDF file content as bytes
        """
        import tempfile

        fd, output_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            self.generate(state, output_path)
            with open(output_path, "rb") as f:
                return f.read()
        finally:
            os.unlink(output_path)
