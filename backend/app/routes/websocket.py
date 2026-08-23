import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.approval_manager import approval_manager
from app.services.connection_manager import manager
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.websocket")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint streaming raw live logs to connected clients."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from logs client: {data}")
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"Logs WebSocket client error: {exc}")
        await manager.disconnect(websocket)


@router.websocket("/ws/agent-thoughts")
async def websocket_agent_thoughts_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint streaming real-time agent reasoning steps (Thinking Terminal)."""
    await thought_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from thoughts client: {data}")
    except WebSocketDisconnect:
        await thought_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"Agent thoughts WebSocket client error: {exc}")
        await thought_manager.disconnect(websocket)


@router.websocket("/ws/pending-approvals")
async def websocket_pending_approvals_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint streaming pending human-in-the-loop approvals (Android App integration)."""
    await approval_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from pending approvals client: {data}")
    except WebSocketDisconnect:
        await approval_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"Pending approvals WebSocket client error: {exc}")
        await approval_manager.disconnect(websocket)
