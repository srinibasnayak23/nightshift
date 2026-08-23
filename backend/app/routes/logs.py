import logging
from fastapi import APIRouter, status
from app.models.log import IngestResponse, LogPayload
from app.services.connection_manager import manager

logger = logging.getLogger("nightshift.logs")

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestResponse,
    summary="Ingest log entry",
    description="Accepts a validated log payload and broadcasts it to all connected WebSocket clients in real time.",
)
async def ingest_log(payload: LogPayload) -> IngestResponse:
    """Ingest a single log payload and broadcast in real time."""
    # Convert model to exact dictionary structure for broadcast
    log_data = {
        "timestamp": payload.timestamp,
        "service": payload.service,
        "level": payload.level.value if hasattr(payload.level, "value") else str(payload.level),
        "message": payload.message,
    }

    logger.info(
        f"Ingested log from [{log_data['service']}] at level [{log_data['level']}]: {log_data['message'][:60]}"
    )

    # Broadcast asynchronously to all connected WebSocket clients
    await manager.broadcast(log_data)

    return IngestResponse(
        status="accepted",
        detail="Log accepted for processing and broadcasting",
    )
