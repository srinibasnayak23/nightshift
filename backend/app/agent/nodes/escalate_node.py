import logging
from datetime import datetime, timezone
from app.agent.state import IncidentState
from app.core.config import settings
from app.services.approval_manager import approval_manager
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.escalate")


def determine_action_type(
    hypothesis: str, error_summary: str, suspect_commit: str
) -> str:
    """
    Determine recommended remediation action ('restart' vs 'rollback').
    - 'restart' for transient issues: memory leaks, OOM, timeouts, deadlocks, connection exhaustion,
      or when no valid suspect commit is present.
    - 'rollback' when hypothesis points to a specific code regression and valid commit SHA.
    """
    combined_text = f"{hypothesis} {error_summary}".lower()
    transient_indicators = [
        "memory",
        "oom",
        "heap",
        "timeout",
        "deadlock",
        "exhaust",
        "leak",
        "hang",
        "unresponsive",
        "socket",
        "gateway timeout",
        "504",
        "502",
    ]

    has_transient_indicator = any(ind in combined_text for ind in transient_indicators)
    has_valid_commit = bool(
        suspect_commit and suspect_commit.lower() not in ("unknown", "none", "")
    )

    if has_transient_indicator or not has_valid_commit:
        return "restart"

    return "rollback"


async def escalate_node(state: IncidentState) -> dict:
    """
    Escalate high-confidence incident for human-in-the-loop review.
    Packages hypothesis, suspect commit, confidence, and recommended action.
    Broadcasts approval request over /ws/pending-approvals WebSocket.
    """
    incident_id = state.get("incident_id", "inc-unknown")
    hypothesis = state.get("hypothesis", "")
    error_summary = state.get("error_summary", "")
    suspect_commit = state.get("suspect_commit", "unknown")
    confidence = float(state.get("confidence", 0.0))

    await thought_manager.broadcast_thought(
        node="escalate_node",
        status="started",
        thought=(
            f"Confidence ({confidence * 100:.1f}%) meets threshold ({settings.confidence_threshold * 100:.0f}%). "
            f"Synthesizing remediation action and escalating incident [{incident_id}] for human approval..."
        ),
    )

    action_type = determine_action_type(hypothesis, error_summary, suspect_commit)

    approval_payload = {
        "incident_id": incident_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "BloHelp",
        "error_summary": error_summary,
        "hypothesis": hypothesis,
        "confidence": confidence,
        "suspect_commit": suspect_commit,
        "action_type": action_type,
        "status": "pending_approval",
    }

    # Broadcast to pending approvals WebSocket subscribers (future Android app)
    await approval_manager.broadcast_pending_approval(approval_payload)

    thought_msg = (
        f"Escalation broadcasted for [{incident_id}]: Recommended action is [{action_type.upper()}] "
        f"(Suspect commit: {suspect_commit}). Awaiting human operator approval."
    )

    await thought_manager.broadcast_thought(
        node="escalate_node",
        status="completed",
        thought=thought_msg,
        confidence=confidence,
        state_updates={
            "action_type": action_type,
            "human_decision": None,
        },
    )

    logger.info("Incident [%s] escalated with action_type=[%s]", incident_id, action_type)

    return {
        "action_type": action_type,
        "human_decision": None,
    }
