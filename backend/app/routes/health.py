from fastapi import APIRouter, status
from app.models.log import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
    description="Returns the operational status of the Nightshift backend service.",
)
async def health_check() -> HealthResponse:
    """Simple health check returning status: ok."""
    return HealthResponse(status="ok")
