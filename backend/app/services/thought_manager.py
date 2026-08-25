import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal
from fastapi import WebSocket

logger = logging.getLogger("nightshift.agent_thoughts")


class ThoughtManager:
    """Manages WebSocket connections and broadcasting for the agent Thinking Terminal."""

    def __init__(self) -> None:
        self._active_connections: set[WebSocket] = set()
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register thought stream subscriber."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
        logger.info(
            f"Thinking Terminal client connected. Active connections: {len(self._active_connections)}"
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister thought stream subscriber."""
        async with self._lock:
            self._active_connections.discard(websocket)
        logger.info(
            f"Thinking Terminal client disconnected. Active connections: {len(self._active_connections)}"
        )

    async def broadcast_thought(
        self,
        node: str,
        status: Literal["started", "completed", "skipped", "error"],
        thought: str,
        state_updates: dict[str, Any] | None = None,
        confidence: float | None = None,
    ) -> None:
        """Broadcast a structured thought event to all connected Thinking Terminal clients."""
        if not self._active_connections:
            return

        event_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "status": status,
            "thought": thought,
            "confidence": confidence,
            "state": state_updates or {},
        }

        text_data = json.dumps(event_payload)

        async with self._lock:
            connections = list(self._active_connections)

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(text_data)
                return None
            except Exception as exc:
                logger.debug(f"Failed to send thought to client ({exc}). Marking for removal.")
                return ws

        results = await asyncio.gather(*[_send(ws) for ws in connections], return_exceptions=True)

        dead_connections = [ws for ws in results if isinstance(ws, WebSocket)]
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self._active_connections.discard(ws)
            logger.info(
                f"Cleaned up {len(dead_connections)} dead Thinking Terminal connection(s). Remaining: {len(self._active_connections)}"
            )


thought_manager = ThoughtManager()
