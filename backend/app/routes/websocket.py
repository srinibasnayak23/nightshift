import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.connection_manager import manager

logger = logging.getLogger("nightshift.websocket")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint streaming live logs to connected clients."""
    await manager.connect(websocket)
    try:
        while True:
            # Await messages from client (keepalive pings, client commands, etc.)
            # If client disconnects or sends text, handle appropriately
            data = await websocket.receive_text()
            logger.debug(f"Received message from client: {data}")
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"WebSocket client error: {exc}")
        await manager.disconnect(websocket)
