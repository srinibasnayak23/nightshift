import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routes import health_router, incidents_router, logs_router, ws_router

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nightshift.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown events."""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}...")
    yield
    logger.info("Shutting down Nightshift ingestion engine...")


def create_app() -> FastAPI:
    """Factory creating and configuring the FastAPI application."""
    application = FastAPI(
        title="Nightshift AI SRE - Ingestion Engine",
        description="Phase 3: Real-time Incident Reasoning, Approvals, and Automated Remediation API",
        version=settings.app_version,
        lifespan=lifespan,
    )

    # Enable CORS for local development with Angular frontend
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API and WebSocket routers
    application.include_router(health_router)
    application.include_router(logs_router)
    application.include_router(incidents_router)
    application.include_router(ws_router)

    return application


app = create_app()
