"""Authenticated, user-scoped WebSocket event delivery."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket

from .auth import VerifiedUser

logger = logging.getLogger(__name__)
WS_SEND_TIMEOUT_SECONDS = 5.0


class ConnectionManager:
    """Only authenticated connections may be registered for an owner's events."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, VerifiedUser] = {}

    def register(self, websocket: WebSocket, user: VerifiedUser) -> None:
        self._connections[websocket] = user
        logger.info("[WS] Authenticated client connected. Total: %s", self.client_count)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def broadcast_to_user(self, user_id: str, message: dict[str, Any]) -> None:
        """The caller supplies the trusted colony owner, never a client message."""
        data = json.dumps(message)

        async def send(websocket: WebSocket, user: VerifiedUser) -> None:
            try:
                if user.expires_at <= time.time():
                    self.disconnect(websocket)
                    await asyncio.wait_for(
                        websocket.close(code=4401), timeout=WS_SEND_TIMEOUT_SECONDS
                    )
                    return
                await asyncio.wait_for(
                    websocket.send_text(data), timeout=WS_SEND_TIMEOUT_SECONDS
                )
            except Exception:
                self.disconnect(websocket)
                try:
                    await asyncio.wait_for(
                        websocket.close(code=1013), timeout=WS_SEND_TIMEOUT_SECONDS
                    )
                except Exception:
                    pass

        await asyncio.gather(*(
            send(websocket, user)
            for websocket, user in list(self._connections.items())
            if user.id == user_id
        ))

    @property
    def client_count(self) -> int:
        return len(self._connections)


ws_manager = ConnectionManager()
