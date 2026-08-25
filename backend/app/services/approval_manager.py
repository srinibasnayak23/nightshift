import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger("nightshift.approvals")


class ApprovalManager:
    """Manages WebSocket connections and pending human-in-the-loop approvals."""

    def __init__(self) -> None:
        self._active_connections: set[WebSocket] = set()
        self._pending_approvals: dict[str, dict[str, Any]] = {}
        self._incident_history: dict[str, dict[str, Any]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register pending approvals subscriber."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
        logger.info(
            "Pending Approvals client connected. Active connections: %d",
            len(self._active_connections),
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister pending approvals subscriber."""
        async with self._lock:
            self._active_connections.discard(websocket)
        logger.info(
            "Pending Approvals client disconnected. Active connections: %d",
            len(self._active_connections),
        )

    async def broadcast_pending_approval(self, payload: dict[str, Any]) -> None:
        """
        Record pending approval in-memory and broadcast payload to all connected clients.
        """
        incident_id = payload.get("incident_id")
        if incident_id:
            async with self._lock:
                self._pending_approvals[incident_id] = payload
                self._incident_history[incident_id] = payload

        if not self._active_connections:
            logger.info(
                "No active WebSocket clients for pending approval [%s]. Stored in-memory.",
                incident_id,
            )
            return

        text_data = json.dumps(payload)

        async with self._lock:
            connections = list(self._active_connections)

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(text_data)
                return None
            except Exception as exc:
                logger.debug("Failed to send approval payload to client (%s). Marking for removal.", exc)
                return ws

        results = await asyncio.gather(*[_send(ws) for ws in connections], return_exceptions=True)

        dead_connections = [ws for ws in results if isinstance(ws, WebSocket)]
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self._active_connections.discard(ws)
            logger.info(
                "Cleaned up %d dead Pending Approvals connection(s). Remaining: %d",
                len(dead_connections),
                len(self._active_connections),
            )

    async def resolve_approval(
        self, incident_id: str, decision: str, execution_result: str | None = None
    ) -> dict[str, Any] | None:
        """Resolve a pending approval when a human decision is submitted."""
        async with self._lock:
            incident = self._pending_approvals.pop(incident_id, None)
            if incident:
                incident["human_decision"] = decision
                incident["status"] = "executed" if decision == "approved" else "rejected"
                incident["resolved_at"] = datetime.now(timezone.utc).isoformat()
                incident["execution_result"] = execution_result
                self._incident_history[incident_id] = incident
            return incident

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """Return list of all currently pending approvals."""
        return list(self._pending_approvals.values())

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        """Retrieve state for an incident by ID."""
        return self._pending_approvals.get(incident_id) or self._incident_history.get(incident_id)


approval_manager = ApprovalManager()
