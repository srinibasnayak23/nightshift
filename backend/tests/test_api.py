import json
import time
from fastapi.testclient import TestClient
from app.agent.graph import run_incident_pipeline


def test_health_check(client: TestClient) -> None:
    """Ensure /health returns 200 and status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_log_ingest_valid_payload(client: TestClient) -> None:
    """Ensure POST /logs/ingest accepts valid payload and returns 202."""
    payload = {
        "timestamp": "2026-08-23T14:30:00.000Z",
        "service": "auth-service",
        "level": "info",
        "message": "User admin logged in successfully",
    }
    response = client.post("/logs/ingest", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "detail" in data


def test_log_ingest_case_insensitive_level(client: TestClient) -> None:
    """Ensure POST /logs/ingest normalizes case-insensitive levels."""
    payload = {
        "service": "payment-gateway",
        "level": "WARN",
        "message": "Payment processing delayed",
    }
    response = client.post("/logs/ingest", json=payload)
    assert response.status_code == 202


def test_log_ingest_auto_timestamp(client: TestClient) -> None:
    """Ensure POST /logs/ingest auto-generates timestamp if missing."""
    payload = {
        "service": "order-processor",
        "level": "error",
        "message": "Order processing failed",
    }
    response = client.post("/logs/ingest", json=payload)
    assert response.status_code == 202


def test_log_ingest_invalid_level(client: TestClient) -> None:
    """Ensure POST /logs/ingest rejects invalid log level with 422."""
    payload = {
        "service": "auth-service",
        "level": "critical_failure",
        "message": "Something went wrong",
    }
    response = client.post("/logs/ingest", json=payload)
    assert response.status_code == 422


def test_log_ingest_empty_service(client: TestClient) -> None:
    """Ensure POST /logs/ingest rejects empty service name with 422."""
    payload = {
        "service": "   ",
        "level": "info",
        "message": "Some message",
    }
    response = client.post("/logs/ingest", json=payload)
    assert response.status_code == 422


def test_log_ingest_empty_message(client: TestClient) -> None:
    """Ensure POST /logs/ingest rejects empty message with 422."""
    payload = {
        "service": "auth-service",
        "level": "info",
        "message": "   ",
    }
    response = client.post("/logs/ingest", json=payload)
    assert response.status_code == 422


def test_websocket_broadcast_on_ingest(client: TestClient) -> None:
    """Ensure connected WebSocket client receives live logs ingested via POST /logs/ingest."""
    with client.websocket_connect("/ws/logs") as websocket:
        payload = {
            "timestamp": "2026-08-23T14:35:00.000Z",
            "service": "inventory-api",
            "level": "warn",
            "message": "Stock level low for SKU-1049",
        }

        # Post the log
        post_response = client.post("/logs/ingest", json=payload)
        assert post_response.status_code == 202

        # Verify WebSocket received the broadcasted log
        raw_msg = websocket.receive_text()
        received_data = json.loads(raw_msg)

        assert received_data["timestamp"] == payload["timestamp"]
        assert received_data["service"] == "inventory-api"
        assert received_data["level"] == "warn"
        assert received_data["message"] == "Stock level low for SKU-1049"


def test_pending_approvals_websocket_stream(client: TestClient) -> None:
    """Ensure /ws/pending-approvals receives approval request when high-confidence error log is ingested."""
    with client.websocket_connect("/ws/pending-approvals") as approval_ws:
        error_payload = {
            "timestamp": "2026-08-23T14:40:00Z",
            "service": "BloHelp",
            "level": "error",
            "message": "Critical connection pool timeout and memory leak in database driver",
        }

        # Ingest the error log
        resp = client.post("/logs/ingest", json=error_payload)
        assert resp.status_code == 202

        # Receive streaming approval payload
        msg_text = approval_ws.receive_text()
        approval_data = json.loads(msg_text)

        assert "incident_id" in approval_data
        assert approval_data["status"] == "pending_approval"
        assert approval_data["action_type"] in ("restart", "rollback", "commit_fix")
        assert approval_data["confidence"] >= 0.7


def test_incident_decision_approve_flow(client: TestClient) -> None:
    """Ensure POST /incidents/{incident_id}/decision with approved triggers execution and returns 200."""
    with client.websocket_connect("/ws/pending-approvals") as approval_ws:
        error_payload = {
            "timestamp": "2026-08-23T14:45:00Z",
            "service": "BloHelp",
            "level": "error",
            "message": "Fatal deadlock on BloHelp billing transaction",
        }

        # Ingest error log
        resp = client.post("/logs/ingest", json=error_payload)
        assert resp.status_code == 202

        # Read pending approval payload
        msg_text = approval_ws.receive_text()
        approval_data = json.loads(msg_text)
        incident_id = approval_data["incident_id"]

        # Submit human approval
        decision_resp = client.post(
            f"/incidents/{incident_id}/decision",
            json={"decision": "approved"},
        )
        assert decision_resp.status_code == 200
        data = decision_resp.json()
        assert data["incident_id"] == incident_id
        assert data["status"] == "executed"
        assert data["decision"] == "approved"
        assert data["execution_result"] is not None


def test_incident_decision_reject_flow(client: TestClient) -> None:
    """Ensure POST /incidents/{incident_id}/decision with rejected cancels execution and returns 200."""
    with client.websocket_connect("/ws/pending-approvals") as approval_ws:
        error_payload = {
            "timestamp": "2026-08-23T14:50:00Z",
            "service": "BloHelp",
            "level": "error",
            "message": "Uncaught exception in BloHelp worker",
        }

        # Ingest error log
        resp = client.post("/logs/ingest", json=error_payload)
        assert resp.status_code == 202

        # Read pending approval payload
        msg_text = approval_ws.receive_text()
        approval_data = json.loads(msg_text)
        incident_id = approval_data["incident_id"]

        # Submit human rejection
        decision_resp = client.post(
            f"/incidents/{incident_id}/decision",
            json={"decision": "rejected"},
        )
        assert decision_resp.status_code == 200
        data = decision_resp.json()
        assert data["incident_id"] == incident_id
        assert data["status"] == "rejected"
        assert data["decision"] == "rejected"
        assert data["execution_result"] is None


def test_incident_decision_invalid_input(client: TestClient) -> None:
    """Ensure POST /incidents/{incident_id}/decision rejects invalid decision value with 422."""
    resp = client.post(
        "/incidents/inc-test-invalid/decision",
        json={"decision": "maybe"},
    )
    assert resp.status_code == 422


def test_incident_decision_not_found(client: TestClient) -> None:
    """Ensure POST /incidents/{incident_id}/decision returns 404 for non-existent incident."""
    resp = client.post(
        "/incidents/inc-nonexistent-99999/decision",
        json={"decision": "approved"},
    )
    assert resp.status_code == 404


def test_list_pending_approvals_api(client: TestClient) -> None:
    """Ensure GET /incidents/pending returns a list of pending items."""
    resp = client.get("/incidents/pending")
    assert resp.status_code == 200
    data = resp.json()
    assert "pending_incidents" in data
    assert isinstance(data["pending_incidents"], list)
