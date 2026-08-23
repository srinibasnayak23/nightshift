import json
import logging
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from app.agent.graph import incident_graph, resume_incident_pipeline
from app.services.approval_manager import approval_manager

logger = logging.getLogger("nightshift.routes.incidents")

router = APIRouter(prefix="/incidents", tags=["Incidents & Approvals"])


class DecisionRequest(BaseModel):
    """Request payload for human approval/rejection decision."""

    decision: str = Field(
        ...,
        description="Human SRE decision: 'approved' or 'rejected'",
        examples=["approved", "rejected"],
    )

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in ("approved", "rejected"):
            raise ValueError("Decision must be either 'approved' or 'rejected'.")
        return val


class DecisionResponse(BaseModel):
    """Response returned after submitting a human decision."""

    incident_id: str
    decision: str
    status: str
    action_type: str | None = None
    execution_result: Any | None = None
    detail: str | None = None


@router.post(
    "/{incident_id}/decision",
    status_code=status.HTTP_200_OK,
    response_model=DecisionResponse,
    summary="Submit human decision for pending incident",
    description="Accepts an approved or rejected decision from human SRE, resumes the LangGraph pipeline, and executes remediation if approved.",
)
async def submit_decision(
    incident_id: str,
    payload: DecisionRequest,
) -> DecisionResponse:
    """Submit human decision to approve or reject incident remediation."""
    decision = payload.decision
    logger.info("Received human decision [%s] for incident [%s]", decision, incident_id)

    # Resume graph execution
    result_state = await resume_incident_pipeline(incident_id=incident_id, decision=decision)

    if result_state.get("status") == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' was not found or is no longer pending.",
        )

    if result_state.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result_state.get("error", "Error resuming incident pipeline"),
        )

    execution_raw = result_state.get("execution_result")
    parsed_execution = None
    if execution_raw:
        try:
            parsed_execution = json.loads(execution_raw)
        except Exception:
            parsed_execution = execution_raw

    final_status = "executed" if decision == "approved" else "rejected"
    detail_msg = (
        f"Incident {incident_id} remediation [{result_state.get('action_type')}] executed successfully."
        if decision == "approved"
        else f"Incident {incident_id} remediation rejected by human operator."
    )

    return DecisionResponse(
        incident_id=incident_id,
        decision=decision,
        status=final_status,
        action_type=result_state.get("action_type"),
        execution_result=parsed_execution,
        detail=detail_msg,
    )


@router.get(
    "/pending",
    status_code=status.HTTP_200_OK,
    summary="List pending approvals",
    description="Returns all currently pending incident approvals awaiting human decision.",
)
async def list_pending_approvals() -> dict[str, list[dict[str, Any]]]:
    """Retrieve all pending approvals."""
    return {"pending_incidents": approval_manager.get_pending_approvals()}


@router.get(
    "/{incident_id}",
    status_code=status.HTTP_200_OK,
    summary="Get incident state",
    description="Returns current state and history of a specific incident.",
)
async def get_incident(incident_id: str) -> dict[str, Any]:
    """Retrieve details for a specific incident."""
    # Try approval manager history first
    record = approval_manager.get_incident(incident_id)
    if record:
        return record

    # Fallback to LangGraph checkpoint state
    config = {"configurable": {"thread_id": incident_id}}
    try:
        graph_state = await incident_graph.aget_state(config)
        if graph_state and graph_state.values:
            return graph_state.values
    except Exception as exc:
        logger.debug("Error reading graph state for [%s]: %s", incident_id, exc)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Incident '{incident_id}' not found.",
    )
