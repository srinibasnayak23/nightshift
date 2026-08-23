import json
import pytest
from fastapi.testclient import TestClient
from app.agent.graph import incident_graph, run_incident_pipeline
from app.agent.nodes import correlate_node, fetch_diff_node, filter_node, summarize_node
from app.agent.state import IncidentState


@pytest.mark.asyncio
async def test_filter_node_non_anomaly() -> None:
    """Ensure non-error logs are classified as non-anomalies."""
    state: IncidentState = {
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
    }
    result = await filter_node(state)
    assert result["is_anomaly"] is False


@pytest.mark.asyncio
async def test_filter_node_anomaly_detection() -> None:
    """Ensure error logs are identified as anomalies."""
    state: IncidentState = {
        "raw_log": json.dumps(
            {
                "timestamp": "2026-08-23T14:30:00Z",
                "service": "payment-gateway",
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
    }
    result = await filter_node(state)
    assert result["is_anomaly"] is True


@pytest.mark.asyncio
async def test_summarize_node() -> None:
    """Ensure summarize_node extracts structured error details."""
    state: IncidentState = {
        "raw_log": json.dumps(
            {
                "service": "payment-gateway",
                "level": "error",
                "message": "Stripe API 500 Internal Server Error during charge capture",
            }
        ),
        "is_anomaly": True,
        "error_summary": "",
        "git_diff": "",
        "suspect_commit": "",
        "hypothesis": "",
        "confidence": 0.0,
    }
    result = await summarize_node(state)
    assert "error_summary" in result
    assert len(result["error_summary"]) > 0


@pytest.mark.asyncio
async def test_fetch_diff_node() -> None:
    """Ensure fetch_diff_node retrieves commit diff and suspect commit."""
    state: IncidentState = {
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Payment gateway timeout",
        "git_diff": "",
        "suspect_commit": "",
        "hypothesis": "",
        "confidence": 0.0,
    }
    result = await fetch_diff_node(state)
    assert "git_diff" in result
    assert "suspect_commit" in result
    assert len(result["suspect_commit"]) > 0


@pytest.mark.asyncio
async def test_correlate_node() -> None:
    """Ensure correlate_node produces hypothesis and strict numeric confidence."""
    state: IncidentState = {
        "raw_log": "error",
        "is_anomaly": True,
        "error_summary": "Database deadlock in payment-gateway",
        "git_diff": "Commit a1b2c3d: Added unindexed foreign key in transactions table",
        "suspect_commit": "a1b2c3d",
        "hypothesis": "",
        "confidence": 0.0,
    }
    result = await correlate_node(state)
    assert "hypothesis" in result
    assert "confidence" in result
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0
    assert len(result["hypothesis"]) > 0


@pytest.mark.asyncio
async def test_full_pipeline_anomaly_execution() -> None:
    """Ensure end-to-end pipeline execution runs all nodes on an error log."""
    log_payload = {
        "timestamp": "2026-08-23T14:35:00Z",
        "service": "order-processor",
        "level": "error",
        "message": "OptimisticLockException during order placement on database replica",
    }
    final_state = await run_incident_pipeline(log_payload)
    assert final_state["is_anomaly"] is True
    assert len(final_state["error_summary"]) > 0
    assert len(final_state["suspect_commit"]) > 0
    assert len(final_state["hypothesis"]) > 0
    assert 0.0 <= final_state["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_full_pipeline_nominal_execution() -> None:
    """Ensure non-error log terminates early at filter_node without LLM calls."""
    log_payload = {
        "timestamp": "2026-08-23T14:35:00Z",
        "service": "auth-service",
        "level": "info",
        "message": "User session token refreshed",
    }
    final_state = await run_incident_pipeline(log_payload)
    assert final_state["is_anomaly"] is False
    assert final_state["error_summary"] == ""
    assert final_state["hypothesis"] == ""


def test_agent_thoughts_websocket_stream(client: TestClient) -> None:
    """Ensure /ws/agent-thoughts streams live reasoning events on error log ingestion."""
    with client.websocket_connect("/ws/agent-thoughts") as thoughts_ws:
        error_payload = {
            "timestamp": "2026-08-23T14:40:00Z",
            "service": "payment-gateway",
            "level": "error",
            "message": "Database deadlock encountered during transaction capture",
        }

        # Ingest the error log
        resp = client.post("/logs/ingest", json=error_payload)
        assert resp.status_code == 202

        # Receive at least one streaming thought event from the background agent pipeline
        msg_text = thoughts_ws.receive_text()
        event_data = json.loads(msg_text)

        assert "node" in event_data
        assert "thought" in event_data
        assert event_data["node"] in [
            "filter_node",
            "summarize_node",
            "fetch_diff_node",
            "correlate_node",
        ]
