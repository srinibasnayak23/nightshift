import json
from fastapi.testclient import TestClient


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
