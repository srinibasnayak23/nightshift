from fastapi import APIRouter, status
from app.models.log import IngestResponse, LogPayload
from app.services.log_service import process_and_ingest_log

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
    return await process_and_ingest_log(payload)

