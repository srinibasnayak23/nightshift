from typing import TypedDict
from pydantic import BaseModel, Field


class IncidentState(TypedDict):
    """LangGraph incident pipeline state."""

    raw_log: str
    is_anomaly: bool
    error_summary: str
    git_diff: str
    suspect_commit: str
    hypothesis: str
    confidence: float


class ErrorSummaryOutput(BaseModel):
    """Structured output for the summarize_node LLM call."""

    error_type: str = Field(
        ...,
        description="Category or type of error (e.g., Timeout, Deadlock, AuthFailure, NullPointer)",
    )
    affected_service: str = Field(
        ...,
        description="Name of the service where the error occurred",
    )
    likely_component: str = Field(
        ...,
        description="Specific component or subsystem within the service (e.g., database pool, oauth handler)",
    )
    summary: str = Field(
        ...,
        description="Concise 1-2 sentence technical summary of the failure",
    )


class CorrelationOutput(BaseModel):
    """Structured output for the correlate_node LLM call."""

    hypothesis: str = Field(
        ...,
        description="Plain-language root cause hypothesis explaining how the suspect commit caused the incident",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score strictly between 0.0 and 1.0",
    )
