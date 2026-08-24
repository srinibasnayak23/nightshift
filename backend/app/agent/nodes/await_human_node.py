import logging
from app.agent.state import IncidentState
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.await_human")


async def await_human_node(state: IncidentState) -> dict:
    """
    Checkpoint / Resume node for human decision.
    When resumed after a decision is submitted, processes the decision and routes to execution or termination.
    """
    incident_id = state.get("incident_id", "inc-unknown")
    human_decision = state.get("human_decision")
    action_type = state.get("action_type", "unknown")

    if human_decision == "approved":
        thought_msg = (
            f"Human approval granted for incident [{incident_id}]. Proceeding to execute remediation [{action_type}]."
        )
    elif human_decision == "rejected":
        thought_msg = (
            f"Human operator REJECTED proposed remediation [{action_type}] for incident [{incident_id}]. Aborting execution."
        )
    else:
        thought_msg = f"Incident [{incident_id}] is awaiting human operator decision..."

    await thought_manager.broadcast_thought(
        node="await_human_node",
        status="completed",
        thought=thought_msg,
        state_updates={"human_decision": human_decision},
    )

    logger.info("Incident [%s] await_human_node: decision=[%s]", incident_id, human_decision)

    return {"human_decision": human_decision}
