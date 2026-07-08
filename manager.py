from fastapi import WebSocket
import uuid
class ConnectionManager:
    def __init__(self):
        # Структура: { room_id: [websocket1, websocket2] }
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, name: str, user_id: str = None) -> str:
        """Принимает подключение, использует существующий user_id или генерирует новый"""
        await websocket.accept()
        
        # Если фронтенд не прислал ID, генерируем новый
        if not user_id:
            import uuid
            user_id = str(uuid.uuid4())
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = {}
            
        # Если пользователь уже был в комнате (например, обновил страницу), 
        # закрываем его старое соединение, чтобы не было дублей
        if user_id in self.active_connections[room_id]:
            try:
                await self.active_connections[room_id][user_id]["ws"].close()
            except Exception:
                pass

        self.active_connections[room_id][user_id] = {
            "ws": websocket,
            "name": name
        }
        
        # Отправляем подтверждение ID обратно клиенту
        await websocket.send_json({"type": "welcome", "user_id": user_id})
        return user_id
    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

    async def broadcast(self, room_id: str, message: dict, exclude: WebSocket = None):
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                if connection != exclude:
                    await connection.send_json(message)
    def get_room_users(self, room_id: str) -> list[dict]:
            """Возвращает список пользователей в комнате"""
            users = []
            if room_id in self.active_connections:
                for u_id, conn in self.active_connections[room_id].items():
                    users.append({"user_id": u_id, "name": conn["name"]})
            return users
    async def broadcast(self, room_id: str, message: dict, exclude_user_id: str = None):
        """Отправляет сообщение всем участникам комнаты (кроме exclude_user_id)"""
        if room_id in self.active_connections:
            # .items() возвращает пару (ключ, значение), то есть (user_id, словарь_с_данными)
            for u_id, conn in self.active_connections[room_id].items():
                if u_id != exclude_user_id:
                    try:
                        # Достаем сам объект websocket из сохраненного словаря
                        await conn["ws"].send_json(message)
                    except Exception:
                        pass
manager = ConnectionManager()