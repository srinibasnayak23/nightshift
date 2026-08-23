from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class LogLevel(str, Enum):
    """Supported log severity levels."""

    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class LogPayload(BaseModel):
    """Ingested log payload structure."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp string",
    )
    service: str = Field(
        ...,
        min_length=1,
        description="Name of the originating service",
    )
    level: LogLevel = Field(
        ...,
        description="Log severity level: info | warn | error",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Log message content",
    )

    @field_validator("service", mode="before")
    @classmethod
    def clean_service(cls, v: str) -> str:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                raise ValueError("Service name cannot be empty or whitespace.")
            return v_stripped
        return v

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, v: str | LogLevel) -> str:
        if isinstance(v, LogLevel):
            return v.value
        if isinstance(v, str):
            v_lower = v.strip().lower()
            if v_lower in ("info", "warn", "error"):
                return v_lower
            # Handle aliases if any (warning -> warn)
            if v_lower in ("warning",):
                return "warn"
            if v_lower in ("err", "critical", "fatal"):
                return "error"
            raise ValueError(f"Invalid log level: '{v}'. Expected 'info', 'warn', or 'error'.")
        raise ValueError(f"Invalid log level type: {type(v).__name__}")

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, v: str | None) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return datetime.now(timezone.utc).isoformat()
        return str(v).strip()

    @field_validator("message", mode="before")
    @classmethod
    def clean_message(cls, v: str) -> str:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                raise ValueError("Log message cannot be empty or whitespace.")
            return v_stripped
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": "2026-08-23T14:30:00.000Z",
                "service": "auth-service",
                "level": "info",
                "message": "User admin logged in successfully",
            }
        }
    }


class IngestResponse(BaseModel):
    """Response returned upon successful log ingestion."""

    status: Literal["accepted"] = "accepted"
    detail: str = "Log accepted for processing and broadcasting"


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["ok"] = "ok"
