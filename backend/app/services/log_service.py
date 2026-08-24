import asyncio
import logging
import uuid
from app.models.log import IngestResponse, LogPayload
from app.services.connection_manager import manager

logger = logging.getLogger("nightshift.services.log")


async def process_and_ingest_log(payload: LogPayload) -> IngestResponse:
    """
    Core in-process log ingestion logic:
    1. Formats log entry.
    2. Broadcasts to /ws/logs WebSocket subscribers.
    3. Triggers LangGraph incident reasoning pipeline asynchronously in background.
    """
    # Lazy import to avoid circular dependency with app.agent.graph
    from app.agent.graph import run_incident_pipeline

    log_data = {
        "timestamp": payload.timestamp,
        "service": payload.service,
        "level": payload.level.value if hasattr(payload.level, "value") else str(payload.level),
        "message": payload.message,
    }

    logger.info(
        "Ingested log from [%s] at level [%s]: %s",
        log_data["service"],
        log_data["level"],
        log_data["message"][:60],
    )

    incident_id = f"inc-{uuid.uuid4().hex[:8]}"

    # 1. Broadcast raw log to /ws/logs subscribers
    await manager.broadcast(log_data)

    # 2. Trigger LangGraph incident reasoning pipeline in background
    asyncio.create_task(run_incident_pipeline(log_data, incident_id=incident_id))

    return IngestResponse(
        status="accepted",
        detail="Log accepted for processing, broadcasting, and agent analysis",
    )
