"""LangGraph-based multi-agent orchestration."""

from typing import Literal

from langgraph.graph import END, StateGraph

from sentinel_agents.agents import (
    AnalystAgent,
    HunterAgent,
    ReporterAgent,
    TriageAgent,
)
from sentinel_agents.state import IncidentState


def should_escalate_to_llm(state: IncidentState) -> Literal["analyst", "end"]:
    """
    Routing logic: escalate to LLM if no high-confidence rule hit.

    Returns:
        "analyst" if LLM analysis needed, "end" otherwise
    """
    # If any rule hit with confidence >= 90, skip LLM
    if any(hit.confidence >= 90 for hit in state.rule_hits):
        return "end"

    return "analyst"


def build_graph() -> StateGraph:
    """
    Build the Sentinel agent graph.

    Flow:
        triage -> [route] -> analyst -> hunter -> reporter -> END
                          -> end (if high confidence)
    """
    workflow = StateGraph(IncidentState)

    # Add nodes
    workflow.add_node("triage", TriageAgent())
    workflow.add_node("analyst", AnalystAgent())
    workflow.add_node("hunter", HunterAgent())
    workflow.add_node("reporter", ReporterAgent())

    # Define edges
    workflow.set_entry_point("triage")

    workflow.add_conditional_edges(
        "triage",
        should_escalate_to_llm,
        {
            "analyst": "analyst",
            "end": END,
        },
    )

    workflow.add_edge("analyst", "hunter")
    workflow.add_edge("hunter", "reporter")
    workflow.add_edge("reporter", END)

    return workflow.compile()


# Global compiled graph
_graph = None


def get_graph():
    """Get or create the compiled graph."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def analyze_log(log: dict) -> IncidentState:
    """
    Analyze a single log event.

    The raw log first passes through the optional preprocessing pipeline
    (field mapping / filters / enrichment). With no preprocessing config the
    pipeline is a zero-overhead no-op. A log dropped by a filter short-
    circuits to a benign, skipped verdict.

    Args:
        log: Log event dictionary

    Returns:
        IncidentState with final verdict
    """
    from sentinel_agents.preprocessing import preprocess
    from sentinel_agents.state import Verdict

    processed = preprocess(log)
    if processed is None:
        # Dropped by a preprocessing filter: nothing to analyze.
        return IncidentState(
            log=log,
            skipped_llm=True,
            verdict=Verdict(
                malicious=False,
                danger_level=0,
                reason="Dropped by preprocessing filter",
            ),
            metadata={"preprocessing": "dropped"},
        )

    graph = get_graph()
    initial_state = IncidentState(log=processed)

    final_state = await graph.ainvoke(initial_state)
    return final_state
