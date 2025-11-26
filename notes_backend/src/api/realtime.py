from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

# Router for WebSocket endpoints to be included by main app
router = APIRouter()


class ConnectionManager:
    """
    Manages active WebSocket connections and broadcasting of messages.

    Tracks connections in-memory. This is suitable for a single-process deployment.
    For multi-process or multi-instance deployments, consider a pub/sub layer (e.g., Redis).
    """

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept a WebSocket connection and add it to the active pool.
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from the active pool.
        """
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """
        Broadcast a JSON-serializable message to all active connections.
        Silently drops connections that fail to receive.
        """
        data = json.dumps(message, default=str)
        async with self._lock:
            targets = list(self.active_connections)
        if not targets:
            return

        coros = []
        for ws in targets:
            coros.append(self._safe_send(ws, data))
        # Use gather to send concurrently while isolating failures
        await asyncio.gather(*coros, return_exceptions=True)

    async def _safe_send(self, websocket: WebSocket, data: str) -> None:
        try:
            await websocket.send_text(data)
        except Exception:
            # Drop broken connections
            await self.disconnect(websocket)


manager = ConnectionManager()


class RealtimeEvent(BaseModel):
    """
    Schema for broadcasted real-time events.
    """
    type: str = Field(..., description="Event type, e.g., note.created, note.updated, note.deleted, tag.created, tag.deleted")
    entity: str = Field(..., description="Entity type, e.g., note or tag")
    action: str = Field(..., description="Action on the entity, e.g., created/updated/deleted")
    payload: Dict[str, Any] = Field(default_factory=dict, description="The entity payload relevant to the event")


async def broadcast_event(entity: str, action: str, payload: Dict[str, Any]) -> None:
    """
    Convenience helper to build and broadcast a standard event.

    Args:
        entity: Entity name (note|tag)
        action: Action name (created|updated|deleted)
        payload: The payload to include (e.g., serialized NoteRead/TagRead)
    """
    event = RealtimeEvent(
        type=f"{entity}.{action}",
        entity=entity,
        action=action,
        payload=payload,
    )
    await manager.broadcast(event.model_dump())


# PUBLIC_INTERFACE
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time updates.

    Clients connect to ws://<host>/ws (or wss:// in production).
    Upon connection, the server will push JSON events on note and tag changes:

    Example event:
    {
      "type": "note.created",
      "entity": "note",
      "action": "created",
      "payload": { ... NoteRead ... }
    }

    The server does not currently process incoming client messages; it only broadcasts.
    """
    await manager.connect(websocket)
    try:
        # Keep connection open and read/discard any incoming messages to detect disconnects.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
