from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Глобальная база комнат в памяти
# Структура: { room_id: { "playlist": ["video1.mp4", "video2.mp4"], "current_index": 0 } }
rooms: dict[str, dict] = {}