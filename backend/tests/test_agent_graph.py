import json
import pytest
from fastapi.testclient import TestClient
from app.agent.graph import (
    incident_graph,
    resume_incident_pipeline,
    run_incident_pipeline,
)
from app.agent.nodes import (
    await_human_node,
    correlate_node,
    determine_action_type,
    escalate_node,
    execute_node,
    fetch_diff_node,
    filter_node,
    low_confidence_node,
    summarize_node,
)
from app.agent.state import IncidentState
from app.agent.tools.render_tool import RenderTool


@pytest.mark.asyncio
async def test_filter_node_non_anomaly() -> None:
    """Ensure non-error logs are classified as non-anomalies."""
    state: IncidentState = {
        "incident_id": "inc-001",
        "raw_log": json.dumps(
            {
                "timestamp": "2026-08-23T14:30:00Z",
                "service": "auth-service",
                "level": "info",
                "message": "User logged in successfully",
            }
        ),
        "is_anomaly": False,
        "error_summary": "",
        "git_diff": "",
        "suspect_commit": "",
        "hypothesis": "",
        "confidence": 0.0,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await filter_node(state)
    assert result["is_anomaly"] is False


@pytest.mark.asyncio
async def test_filter_node_anomaly_detection() -> None:
    """Ensure error logs are identified as anomalies."""
    state: IncidentState = {
        "incident_id": "inc-002",
        "raw_log": json.dumps(
            {
                "timestamp": "2026-08-23T14:30:00Z",
                "service": "BloHelp",
                "level": "error",
                "message": "Database deadlock encountered during transaction #84102",
            }
        ),
        "is_anomaly": False,
        "error_summary": "",
        "git_diff": "",
        "suspect_commit": "",
        "hypothesis": "",
        "confidence": 0.0,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await filter_node(state)
    assert result["is_anomaly"] is True


@pytest.mark.asyncio
async def test_summarize_node() -> None:
    """Ensure summarize_node extracts structured error details."""
    state: IncidentState = {
        "incident_id": "inc-003",
        "raw_log": json.dumps(
            {
                "service": "BloHelp",
                "level": "error",
                "message": "Out of memory error in worker process",
            }
        ),
        "is_anomaly": True,
        "error_summary": "",
        "git_diff": "",
        "suspect_commit": "",
        "hypothesis": "",
        "confidence": 0.0,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await summarize_node(state)
    assert "error_summary" in result
    assert len(result["error_summary"]) > 0


@pytest.mark.asyncio
async def test_fetch_diff_node() -> None:
    """Ensure fetch_diff_node retrieves commit diff and suspect commit."""
    state: IncidentState = {
        "incident_id": "inc-004",
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Gateway timeout 504 in BloHelp API",
        "git_diff": "",
        "suspect_commit": "",
        "hypothesis": "",
        "confidence": 0.0,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await fetch_diff_node(state)
    assert "git_diff" in result
    assert "suspect_commit" in result
    assert len(result["suspect_commit"]) > 0


@pytest.mark.asyncio
async def test_correlate_node() -> None:
    """Ensure correlate_node produces hypothesis and strict numeric confidence."""
    state: IncidentState = {
        "incident_id": "inc-005",
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Database deadlock in BloHelp",
        "git_diff": "Commit a1b2c3d: Added unindexed foreign key in transactions table",
        "suspect_commit": "a1b2c3d",
        "suspect_commit_deploy_status": "live",
        "hypothesis": "",
        "confidence": 0.0,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await correlate_node(state)
    assert "hypothesis" in result
    assert "confidence" in result
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0
    assert len(result["hypothesis"]) > 0


@pytest.mark.asyncio
async def test_correlate_node_literal_typo_diff() -> None:
    """Ensure correlate_node detects literal typo in diff (MNGO_URI vs MONGO_URI) with high confidence."""
    state: IncidentState = {
        "incident_id": "inc-typo-1",
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "MongoServerError: Authentication failed (MNGO_URI missing)",
        "git_diff": "--- a/.env\n+++ b/.env\n- MONGO_URI=mongodb://localhost:27017/blohelp\n+ MNGO_URI=mongodb://localhost:27017/blohelp",
        "suspect_commit": "d6f21dce",
        "suspect_commit_deploy_status": "live",
        "hypothesis": "",
        "confidence": 0.0,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await correlate_node(state)
    assert "mngo_uri" in result["hypothesis"].lower() or "mongo_uri" in result["hypothesis"].lower()
    assert result["confidence"] >= 0.85


@pytest.mark.asyncio
async def test_correlate_node_failed_deploy_lowers_confidence() -> None:
    """Ensure correlate_node lowers confidence and notes non-live status when deploy failed on Render."""
    state: IncidentState = {
        "incident_id": "inc-failed-deploy-1",
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Critical error in BloHelp",
        "git_diff": "--- a/app.js\n+++ b/app.js\n+ const broken = null.property;",
        "suspect_commit": "d6f21dce",
        "suspect_commit_deploy_status": "update_failed",
        "hypothesis": "",
        "confidence": 0.0,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await correlate_node(state)
    assert "not live" in result["hypothesis"].lower() or "failed to deploy" in result["hypothesis"].lower()
    assert result["confidence"] <= 0.50


def test_determine_action_type() -> None:
    """Ensure action_type heuristic accurately distinguishes restart vs rollback vs none."""
    # Failed deploy -> none
    assert (
        determine_action_type(
            hypothesis="Code has typo but never deployed",
            error_summary="SyntaxError",
            suspect_commit="d6f21dce",
            deploy_status="update_failed",
        )
        == "none"
    )

    # Transient issues -> restart
    assert (
        determine_action_type(
            hypothesis="Memory leak causing OOM",
            error_summary="OutOfMemoryException",
            suspect_commit="a1b2c3d",
            deploy_status="live",
        )
        == "restart"
    )
    assert (
        determine_action_type(
            hypothesis="Gateway timeout under heavy load",
            error_summary="504 Gateway Timeout",
            suspect_commit="a1b2c3d",
            deploy_status="live",
        )
        == "restart"
    )
    assert (
        determine_action_type(
            hypothesis="Database lock contention",
            error_summary="Deadlock detected",
            suspect_commit="unknown",
            deploy_status=None,
        )
        == "restart"
    )

    # Code regression with valid live suspect commit -> rollback
    assert (
        determine_action_type(
            hypothesis="Commit breaking API contract for auth token validation",
            error_summary="NullPointerException in AuthService.ts",
            suspect_commit="8f3e21a",
            deploy_status="live",
        )
        == "rollback"
    )


@pytest.mark.asyncio
async def test_escalate_node() -> None:
    """Ensure escalate_node packages payload and recommends action."""
    state: IncidentState = {
        "incident_id": "inc-escalate-1",
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Heap memory limit exceeded in BloHelp",
        "git_diff": "Commit diff details",
        "suspect_commit": "7f2a18b",
        "hypothesis": "Memory exhaustion due to unclosed socket connections",
        "confidence": 0.85,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await escalate_node(state)
    assert result["action_type"] == "restart"
    assert result["human_decision"] is None


@pytest.mark.asyncio
async def test_low_confidence_node() -> None:
    """Ensure low_confidence_node marks incident as requiring manual investigation."""
    state: IncidentState = {
        "incident_id": "inc-low-1",
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Intermittent packet drop",
        "git_diff": "",
        "suspect_commit": "unknown",
        "hypothesis": "Unclear root cause",
        "confidence": 0.35,
        "human_decision": None,
        "action_type": None,
        "execution_result": None,
    }
    result = await low_confidence_node(state)
    assert result["execution_result"] == "needs_manual_investigation"
    assert result["action_type"] is None
    assert result["human_decision"] is None


@pytest.mark.asyncio
async def test_execute_node_safety_guardrail() -> None:
    """Ensure execute_node throws an exception if human_decision != 'approved'."""
    unapproved_state: IncidentState = {
        "incident_id": "inc-safe-1",
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Critical error",
        "git_diff": "",
        "suspect_commit": "7f2a18b",
        "hypothesis": "Regression bug",
        "confidence": 0.9,
        "human_decision": None,  # Not approved!
        "action_type": "restart",
        "execution_result": None,
    }
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION"):
        await execute_node(unapproved_state)


@pytest.mark.asyncio
async def test_execute_node_approved() -> None:
    """Ensure execute_node successfully performs remediation when approved."""
    approved_state: IncidentState = {
        "incident_id": "inc-safe-2",
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Critical error",
        "git_diff": "",
        "suspect_commit": "7f2a18b",
        "hypothesis": "Regression bug",
        "confidence": 0.9,
        "human_decision": "approved",
        "action_type": "restart",
        "execution_result": None,
    }
    result = await execute_node(approved_state)
    assert "execution_result" in result
    assert result["execution_result"] is not None
    exec_data = json.loads(result["execution_result"])
    assert exec_data["action"] == "restart"
    assert exec_data["status"] == "success"


@pytest.mark.asyncio
async def test_render_tool_simulated_methods() -> None:
    """Ensure RenderTool operates safely in simulated mode when credentials are not configured."""
    tool = RenderTool(api_key="", default_service_id="srv-blohelp-123")
    restart_res = await tool.restart_service()
    assert restart_res["success"] is True
    assert restart_res["action"] == "restart"
    assert restart_res["simulated"] is True

    rollback_res = await tool.rollback_deployment(commit_id="7f2a18b")
    assert rollback_res["success"] is True
    assert rollback_res["action"] == "rollback"
    assert rollback_res["simulated"] is True

    deploy_status = await tool.get_deploy_status_for_commit(commit_sha="7f2a18b")
    assert deploy_status == "live"



@pytest.mark.asyncio
async def test_full_pipeline_with_approval_and_execution() -> None:
    """
    Ensure end-to-end flow:
    1. Ingest anomaly log with live deploy -> pipeline halts at await_human_node checkpoint
    2. Resume pipeline with 'approved' -> execute_node runs and produces execution_result
    """
    from unittest.mock import AsyncMock, patch

    log_payload = {
        "timestamp": "2026-08-23T14:35:00Z",
        "service": "BloHelp",
        "level": "error",
        "message": "Database deadlock encountered during transaction",
    }
    incident_id = "inc-test-approval-1"

    with patch("app.agent.nodes.fetch_diff_node.render_tool.get_deploy_status_for_commit", new_callable=AsyncMock) as mock_deploy:
        mock_deploy.return_value = "live"

        # Step 1: Initial execution
        paused_state = await run_incident_pipeline(log_payload, incident_id=incident_id)
        assert paused_state["is_anomaly"] is True
        assert paused_state["confidence"] >= 0.7
        assert paused_state["action_type"] in ("restart", "rollback")
        assert paused_state["human_decision"] is None

        # Step 2: Resume with approved
        final_state = await resume_incident_pipeline(incident_id=incident_id, decision="approved")
        assert final_state["human_decision"] == "approved"
        assert final_state["execution_result"] is not None
        exec_res = json.loads(final_state["execution_result"])
        assert exec_res["status"] == "success"


@pytest.mark.asyncio
async def test_full_pipeline_with_rejection() -> None:
    """
    Ensure end-to-end flow with rejection:
    1. Ingest anomaly log -> pipeline halts at await_human_node
    2. Resume pipeline with 'rejected' -> execute_node NEVER runs
    """
    from unittest.mock import AsyncMock, patch

    log_payload = {
        "timestamp": "2026-08-23T14:35:00Z",
        "service": "BloHelp",
        "level": "error",
        "message": "Database deadlock encountered during transaction",
    }
    incident_id = "inc-test-rejection-1"

    with patch("app.agent.nodes.fetch_diff_node.render_tool.get_deploy_status_for_commit", new_callable=AsyncMock) as mock_deploy:
        mock_deploy.return_value = "live"

        # Step 1: Initial execution
        paused_state = await run_incident_pipeline(log_payload, incident_id=incident_id)
        assert paused_state["confidence"] >= 0.7

        # Step 2: Resume with rejected
        final_state = await resume_incident_pipeline(incident_id=incident_id, decision="rejected")
        assert final_state["human_decision"] == "rejected"
        # execute_node was skipped, so execution_result remains None
        assert final_state.get("execution_result") is None


@pytest.mark.asyncio
async def test_full_pipeline_with_failed_deploy() -> None:
    """
    Ensure end-to-end flow when commit deploy failed:
    Pipeline identifies non-live status, assigns low confidence, routes to low_confidence_node, and never halts for approval.
    """
    from unittest.mock import AsyncMock, patch

    log_payload = {
        "timestamp": "2026-08-23T14:35:00Z",
        "service": "BloHelp",
        "level": "error",
        "message": "SyntaxError: Unexpected token in app.js",
    }
    incident_id = "inc-test-nonlive-1"

    with patch("app.agent.nodes.fetch_diff_node.render_tool.get_deploy_status_for_commit", new_callable=AsyncMock) as mock_deploy:
        mock_deploy.return_value = "update_failed"

        final_state = await run_incident_pipeline(log_payload, incident_id=incident_id)
        assert final_state["is_anomaly"] is True
        assert final_state["confidence"] < 0.7
        assert final_state["action_type"] is None
        assert final_state["execution_result"] == "needs_manual_investigation"
        assert "not live" in final_state["hypothesis"].lower() or "failed to deploy" in final_state["hypothesis"].lower()

