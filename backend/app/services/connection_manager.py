import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger("nightshift.websocket")


class ConnectionManager:
    """Manages active WebSocket connections and broadcasting."""

    def __init__(self) -> None:
        self._active_connections: set[WebSocket] = set()
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept connection and register client."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
        logger.info(
            f"WebSocket client connected. Active connections: {len(self._active_connections)}"
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister client gracefully."""
        async with self._lock:
            self._active_connections.discard(websocket)
        logger.info(
            f"WebSocket client disconnected. Active connections: {len(self._active_connections)}"
        )

    async def broadcast(self, message: dict[str, Any] | str) -> None:
        """Broadcast payload to all connected clients concurrently."""
        if not self._active_connections:
            return

        async with self._lock:
            connections = list(self._active_connections)

        if isinstance(message, dict):
            text_data = json.dumps(message)
        else:
            text_data = str(message)

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(text_data)
                return None
            except Exception as exc:
                logger.debug(f"Failed to send to client ({exc}). Marking for removal.")
                return ws

        results = await asyncio.gather(*[_send(ws) for ws in connections], return_exceptions=True)

        # Clean up any dead connections
        dead_connections = [ws for ws in results if isinstance(ws, WebSocket)]
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self._active_connections.discard(ws)
            logger.info(
                f"Cleaned up {len(dead_connections)} dead WebSocket connection(s). Remaining: {len(self._active_connections)}"
            )


# Global singleton connection manager
manager = ConnectionManager()
