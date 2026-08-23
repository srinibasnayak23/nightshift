import json
import logging
from datetime import datetime, timezone
from app.agent.state import IncidentState
from app.agent.tools.render_tool import render_tool
from app.core.config import settings
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.execute")


async def execute_node(state: IncidentState) -> dict:
    """
    Automated execution node for approved remediation actions.
    Enforces strict safety verification: human_decision MUST be 'approved'.
    Calls Render API tool for service restart or rollback deployment.
    """
    human_decision = state.get("human_decision")
    action_type = state.get("action_type")
    incident_id = state.get("incident_id", "inc-unknown")
    suspect_commit = state.get("suspect_commit", "")
    target_service_id = settings.render_target_service_id or "BloHelp"

    # STRICT SAFETY INVARIANT: Execution cannot run without human approval
    if human_decision != "approved":
        error_msg = (
            f"SAFETY VIOLATION: execute_node triggered for incident [{incident_id}] "
            f"without explicit approval (human_decision='{human_decision}'). Execution blocked."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    await thought_manager.broadcast_thought(
        node="execute_node",
        status="started",
        thought=f"Executing approved remediation action [{action_type}] on Render for service [{target_service_id}]...",
    )

    execution_timestamp = datetime.now(timezone.utc).isoformat()
    raw_result: dict = {}

    try:
        if action_type == "restart":
            logger.info("Triggering Render service restart for [%s]...", target_service_id)
            raw_result = await render_tool.restart_service(service_id=target_service_id)
        elif action_type == "rollback":
            logger.info(
                "Triggering Render deployment rollback for [%s] to commit [%s]...",
                target_service_id,
                suspect_commit,
            )
            raw_result = await render_tool.rollback_deployment(
                service_id=target_service_id,
                commit_id=suspect_commit if suspect_commit != "unknown" else None,
            )
        else:
            raw_result = {
                "success": False,
                "action": action_type,
                "error": f"Unknown action_type: '{action_type}'.",
            }
    except Exception as exc:
        logger.error(
            "Unexpected error during Render tool invocation: %s", exc, exc_info=True
        )
        raw_result = {
            "success": False,
            "action": action_type,
            "error": f"Execution error: {str(exc)}",
        }

    is_success = raw_result.get("success", False)
    status_str = "SUCCESS" if is_success else "FAILED"
    result_detail = raw_result.get("message") or raw_result.get("error", "No details")

    # Structured Audit Log
    logger.info(
        "[AUDIT EXECUTION] Timestamp: %s | IncidentID: %s | User: Human SRE | Action: %s | Service: %s | Commit: %s | Status: %s | Result: %s",
        execution_timestamp,
        incident_id,
        action_type,
        target_service_id,
        suspect_commit,
        status_str,
        result_detail,
    )

    execution_result = json.dumps(
        {
            "status": status_str.lower(),
            "action": action_type,
            "timestamp": execution_timestamp,
            "details": raw_result,
        }
    )

    thought_msg = (
        f"Remediation [{action_type}] completed with status [{status_str}]. {result_detail}"
    )

    await thought_manager.broadcast_thought(
        node="execute_node",
        status="completed" if is_success else "error",
        thought=thought_msg,
        state_updates={"execution_result": execution_result},
    )

    return {"execution_result": execution_result}
