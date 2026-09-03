import asyncio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[WebSocket, asyncio.Queue] = {}

    async def connect(self, websocket: WebSocket, snapshot: dict):
        await websocket.accept()
        queue: asyncio.Queue = asyncio.Queue()
        self.active[websocket] = queue
        queue.put_nowait({"type": "snapshot", "data": snapshot})

    def disconnect(self, websocket: WebSocket):
        self.active.pop(websocket, None)

    async def broadcast(self, delta: dict):
        for queue in self.active.values():
            queue.put_nowait({"type": "delta", "data": delta})