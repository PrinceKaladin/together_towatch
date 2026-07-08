import asyncio
from typing import Optional
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, room_id: str):
        await ws.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = []
        self.rooms[room_id].append(ws)
        await self.broadcast_viewers(room_id)

    def disconnect(self, ws: WebSocket, room_id: str):
        if room_id in self.rooms:
            try:
                self.rooms[room_id].remove(ws)
            except ValueError:
                pass
        asyncio.create_task(self.broadcast_viewers(room_id))

    async def broadcast(self, room_id: str, message: dict, exclude: Optional[WebSocket] = None):
        if room_id not in self.rooms:
            return
        dead = []
        for ws in self.rooms[room_id]:
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self.rooms[room_id].remove(ws)
            except ValueError:
                pass

    async def broadcast_viewers(self, room_id: str):
        count = len(self.rooms.get(room_id, []))
        await self.broadcast(room_id, {"type": "viewers", "count": count})

manager = ConnectionManager()