import json
import logging
from app.agent.state import IncidentState
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.filter")

ERROR_KEYWORDS = {
    "error",
    "err",
    "fatal",
    "critical",
    "exception",
    "timeout",
    "timed out",
    "deadlock",
    "refused",
    "corrupt",
    "500 internal server error",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
    "outofmemory",
    "sigterm",
    "sigsegv",
    "panic",
}


async def filter_node(state: IncidentState) -> dict:
    """
    NON-LLM anomaly pre-filter cost gate.
    Evaluates log severity and keyword patterns without expensive LLM calls.
    """
    raw_log = state.get("raw_log", "")
    is_anomaly = False
    service_name = "unknown"
    level = "info"

    # Try parsing JSON structure if available
    try:
        if isinstance(raw_log, str) and raw_log.strip().startswith("{"):
            log_data = json.loads(raw_log)
            level = str(log_data.get("level", "")).lower()
            service_name = str(log_data.get("service", "unknown"))
            message = str(log_data.get("message", "")).lower()

            if level in ("error", "fatal", "critical"):
                is_anomaly = True
            elif any(kw in message for kw in ERROR_KEYWORDS):
                is_anomaly = True
        else:
            raw_lower = raw_log.lower()
            if any(kw in raw_lower for kw in ERROR_KEYWORDS):
                is_anomaly = True
    except Exception as exc:
        logger.warning(f"Error parsing raw_log in filter_node ({exc}). Flagging as anomaly.")
        is_anomaly = True

    if is_anomaly:
        thought_msg = f"Anomaly detected in log from [{service_name}] (level: {level}). Escalating to LLM reasoning."
        status = "completed"
    else:
        thought_msg = f"Log from [{service_name}] is nominal (level: {level}). Bypassing LLM pipeline."
        status = "skipped"

    await thought_manager.broadcast_thought(
        node="filter_node",
        status=status,
        thought=thought_msg,
        state_updates={"is_anomaly": is_anomaly},
    )

    return {"is_anomaly": is_anomaly}
