import asyncio
import logging
import uuid
from fastapi import APIRouter, status
from app.agent.graph import run_incident_pipeline
from app.models.log import IngestResponse, LogPayload
from app.services.connection_manager import manager

logger = logging.getLogger("nightshift.logs")

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestResponse,
    summary="Ingest log entry",
    description="Accepts a validated log payload, broadcasts it to /ws/logs, and triggers the LangGraph reasoning pipeline asynchronously.",
)
async def ingest_log(payload: LogPayload) -> IngestResponse:
    """Ingest a single log payload, broadcast to /ws/logs, and execute LangGraph pipeline."""
    log_data = {
        "timestamp": payload.timestamp,
        "service": payload.service,
        "level": payload.level.value if hasattr(payload.level, "value") else str(payload.level),
        "message": payload.message,
    }

    logger.info(
        f"Ingested log from [{log_data['service']}] at level [{log_data['level']}]: {log_data['message'][:60]}"
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
