"""WebSocket connection manager for live updates."""

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[user_id].append(ws)

    def disconnect(self, user_id: str, ws: WebSocket) -> None:
        if ws in self._connections.get(user_id, []):
            self._connections[user_id].remove(ws)

    async def send_to_user(self, user_id: str, event: str, payload: dict) -> None:
        message = json.dumps({"event": event, "payload": payload})
        stale = []
        for ws in self._connections.get(user_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(user_id, ws)

    async def broadcast(self, event: str, payload: dict) -> None:
        for user_id in list(self._connections):
            await self.send_to_user(user_id, event, payload)


manager = ConnectionManager()
