import logging
from app.agent.state import IncidentState
from app.core.config import settings
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.low_confidence")


async def low_confidence_node(state: IncidentState) -> dict:
    """
    Handles incidents where root-cause correlation confidence is below threshold.
    Marks incident as requiring manual SRE investigation with no automated remediation.
    """
    incident_id = state.get("incident_id", "inc-unknown")
    confidence = float(state.get("confidence", 0.0))
    threshold = settings.confidence_threshold

    thought_msg = (
        f"Correlation confidence ({confidence * 100:.1f}%) is below escalation threshold ({threshold * 100:.0f}%). "
        f"Marking incident [{incident_id}] as requiring manual SRE investigation. No automated action proposed."
    )

    await thought_manager.broadcast_thought(
        node="low_confidence_node",
        status="completed",
        thought=thought_msg,
        confidence=confidence,
        state_updates={
            "action_type": None,
            "human_decision": None,
            "execution_result": "needs_manual_investigation",
        },
    )

    logger.info(
        "Incident [%s] marked for manual investigation (confidence=%.2f < threshold=%.2f)",
        incident_id,
        confidence,
        threshold,
    )

    return {
        "action_type": None,
        "human_decision": None,
        "execution_result": "needs_manual_investigation",
    }
