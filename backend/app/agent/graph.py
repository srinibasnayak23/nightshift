import json
import logging
from typing import Any
from langgraph.graph import END, StateGraph
from app.agent.nodes import (
    correlate_node,
    fetch_diff_node,
    filter_node,
    summarize_node,
)
from app.agent.state import IncidentState

logger = logging.getLogger("nightshift.agent.graph")


def route_after_filter(state: IncidentState) -> str:
    """Conditional edge routing: anomaly -> summarize_node, otherwise -> END."""
    if state.get("is_anomaly", False):
        return "summarize_node"
    return END


def build_incident_graph() -> Any:
    """Build and compile the LangGraph incident analysis workflow."""
    workflow = StateGraph(IncidentState)

    # Register Nodes
    workflow.add_node("filter_node", filter_node)
    workflow.add_node("summarize_node", summarize_node)
    workflow.add_node("fetch_diff_node", fetch_diff_node)
    workflow.add_node("correlate_node", correlate_node)

    # Set Entry Point
    workflow.set_entry_point("filter_node")

    # Define Edges
    workflow.add_conditional_edges(
        "filter_node",
        route_after_filter,
        {
            "summarize_node": "summarize_node",
            END: END,
        },
    )
    workflow.add_edge("summarize_node", "fetch_diff_node")
    workflow.add_edge("fetch_diff_node", "correlate_node")
    workflow.add_edge("correlate_node", END)

    return workflow.compile()


# Global compiled workflow graph
incident_graph = build_incident_graph()


async def run_incident_pipeline(raw_log: dict | str) -> dict[str, Any]:
    """
    Execute the LangGraph incident pipeline for a given log payload.
    Returns the final state of the pipeline.
    """
    raw_log_str = json.dumps(raw_log) if isinstance(raw_log, dict) else str(raw_log)

    initial_state: IncidentState = {
        "raw_log": raw_log_str,
        "is_anomaly": False,
        "error_summary": "",
        "git_diff": "",
        "suspect_commit": "",
        "hypothesis": "",
        "confidence": 0.0,
    }

    try:
        final_state = await incident_graph.ainvoke(initial_state)
        logger.info(
            "Incident pipeline finished for log. Anomaly=%s, Confidence=%.2f",
            final_state.get("is_anomaly", False),
            final_state.get("confidence", 0.0),
        )
        return final_state
    except Exception as exc:
        logger.error("Error executing incident pipeline graph: %s", exc, exc_info=True)
        return initial_state
