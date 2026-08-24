import json
import logging
import uuid
from typing import Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from app.agent.nodes import (
    await_human_node,
    correlate_node,
    escalate_node,
    execute_node,
    fetch_diff_node,
    filter_node,
    low_confidence_node,
    summarize_node,
)
from app.agent.state import IncidentState
from app.core.config import settings
from app.services.approval_manager import approval_manager

logger = logging.getLogger("nightshift.agent.graph")


def route_after_filter(state: IncidentState) -> str:
    """Conditional edge routing: anomaly -> summarize_node, otherwise -> END."""
    if state.get("is_anomaly", False):
        return "summarize_node"
    return END


def route_after_correlate(state: IncidentState) -> str:
    """
    Conditional edge routing:
    confidence >= threshold -> escalate_node,
    confidence < threshold -> low_confidence_node.
    """
    confidence = float(state.get("confidence", 0.0))
    if confidence >= settings.confidence_threshold:
        return "escalate_node"
    return "low_confidence_node"


def route_after_await_human(state: IncidentState) -> str:
    """
    Conditional edge routing:
    human_decision == 'approved' -> execute_node,
    human_decision == 'rejected' or others -> END.
    """
    decision = state.get("human_decision")
    if decision == "approved":
        return "execute_node"
    return END


def build_incident_graph() -> Any:
    """Build and compile the LangGraph incident analysis and remediation workflow with checkpointing."""
    workflow = StateGraph(IncidentState)

    # Register Nodes
    workflow.add_node("filter_node", filter_node)
    workflow.add_node("summarize_node", summarize_node)
    workflow.add_node("fetch_diff_node", fetch_diff_node)
    workflow.add_node("correlate_node", correlate_node)
    workflow.add_node("escalate_node", escalate_node)
    workflow.add_node("low_confidence_node", low_confidence_node)
    workflow.add_node("await_human_node", await_human_node)
    workflow.add_node("execute_node", execute_node)

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

    workflow.add_conditional_edges(
        "correlate_node",
        route_after_correlate,
        {
            "escalate_node": "escalate_node",
            "low_confidence_node": "low_confidence_node",
        },
    )

    workflow.add_edge("low_confidence_node", END)
    workflow.add_edge("escalate_node", "await_human_node")

    workflow.add_conditional_edges(
        "await_human_node",
        route_after_await_human,
        {
            "execute_node": "execute_node",
            END: END,
        },
    )

    workflow.add_edge("execute_node", END)

    # Compile with MemorySaver and interrupt before human approval
    checkpointer = MemorySaver()
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_human_node"],
    )


# Global compiled workflow graph
incident_graph = build_incident_graph()


async def run_incident_pipeline(
    raw_log: dict | str, incident_id: str | None = None
) -> dict[str, Any]:
    """
    Execute the LangGraph incident pipeline for a given log payload.
    If high confidence, executes until interrupted before await_human_node.
    """
    inc_id = incident_id or f"inc-{uuid.uuid4().hex[:8]}"
    raw_log_str = json.dumps(raw_log) if isinstance(raw_log, dict) else str(raw_log)

    initial_state: IncidentState = {
        "incident_id": inc_id,
        "raw_log": raw_log_str,
        "is_anomaly": False,
        "error_summary": "",
        "git_diff": "",
        "suspect_commit": "",
        "hypothesis": "",
        "confidence": 0.0,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }

    config = {"configurable": {"thread_id": inc_id}}

    try:
        final_state = await incident_graph.ainvoke(initial_state, config=config)
        logger.info(
            "Incident pipeline run for [%s]. Anomaly=%s, Confidence=%.2f, Action=%s",
            inc_id,
            final_state.get("is_anomaly", False),
            final_state.get("confidence", 0.0),
            final_state.get("action_type"),
        )
        return final_state
    except Exception as exc:
        logger.error("Error executing incident pipeline graph for [%s]: %s", inc_id, exc, exc_info=True)
        return initial_state


async def resume_incident_pipeline(incident_id: str, decision: str) -> dict[str, Any]:
    """
    Resume an interrupted incident pipeline with a human operator decision ('approved' or 'rejected').
    """
    normalized_decision = decision.strip().lower()
    if normalized_decision not in ("approved", "rejected"):
        raise ValueError(f"Invalid decision '{decision}'. Must be 'approved' or 'rejected'.")

    config = {"configurable": {"thread_id": incident_id}}

    try:
        # Check current state in checkpointer
        current_state = await incident_graph.aget_state(config)
        if not current_state or not current_state.values:
            logger.warning("No checkpoint found for incident_id [%s].", incident_id)
            return {
                "incident_id": incident_id,
                "status": "not_found",
                "error": f"No active or interrupted incident found for id '{incident_id}'.",
            }

        # Update state with human decision
        await incident_graph.aupdate_state(config, {"human_decision": normalized_decision})

        # Resume graph execution
        final_state = await incident_graph.ainvoke(None, config=config)

        execution_res = final_state.get("execution_result")
        logger.info(
            "Incident [%s] resumed with decision [%s]. Final status: %s",
            incident_id,
            normalized_decision,
            "executed" if normalized_decision == "approved" else "rejected",
        )

        # Update approval manager
        await approval_manager.resolve_approval(
            incident_id=incident_id,
            decision=normalized_decision,
            execution_result=execution_res,
        )

        return final_state

    except Exception as exc:
        logger.error("Error resuming incident pipeline [%s]: %s", incident_id, exc, exc_info=True)
        return {
            "incident_id": incident_id,
            "status": "error",
            "error": str(exc),
        }
