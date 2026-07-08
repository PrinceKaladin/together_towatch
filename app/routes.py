import uuid
from pathlib import Path
from fastapi import APIRouter, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

from app.config import UPLOAD_DIR, rooms
from app.manager import manager

router = APIRouter()

# Хелпер для сканирования видео на старте
def scan_uploads():
    for room_dir in UPLOAD_DIR.iterdir():
        if not room_dir.is_dir():
            continue
        room_id = room_dir.name
        if room_id in rooms:
            continue
        videos = [
            f.name for f in room_dir.iterdir()
            if f.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv", ".avi")
        ]
        if videos:
            rooms[room_id] = {"playlist": videos, "current_index": 0}

scan_uploads()

@router.get("/", response_class=HTMLResponse)
@router.get("/room/{room_id}", response_class=HTMLResponse)
async def get_index():
    index_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))

@router.get("/room-info/{room_id}")
async def room_info(room_id: str):
    if room_id in rooms:
        return JSONResponse(rooms[room_id])
    return JSONResponse({"playlist": [], "current_index": 0})

@router.post("/upload/{room_id}")
async def upload(room_id: str, file: UploadFile = File(...)):
    # Если комната новая/лобби — генерируем нормальный ID комнаты
    actual_room_id = room_id if room_id != "lobby" else str(uuid.uuid4())[:8]
    
    room_dir = UPLOAD_DIR / actual_room_id
    room_dir.mkdir(exist_ok=True)

    safe_name = Path(file.filename).name
    dest = room_dir / safe_name

    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    if actual_room_id not in rooms:
        rooms[actual_room_id] = {"playlist": [], "current_index": 0}
    
    if safe_name not in rooms[actual_room_id]["playlist"]:
        rooms[actual_room_id]["playlist"].append(safe_name)

    return JSONResponse({
        "room_id": actual_room_id, 
        "filename": safe_name, 
        "playlist": rooms[actual_room_id]["playlist"]
    })

@router.get("/video/{room_id}/{filename}")
async def stream_video(room_id: str, filename: str, request: Request):
    path = UPLOAD_DIR / room_id / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)

    file_size = path.stat().st_size
    ext = path.suffix.lower()
    content_type = {
        ".mp4": "video/mp4", ".webm": "video/webm",
        ".mov": "video/quicktime", ".mkv": "video/x-matroska"
    }.get(ext, "video/mp4")

    range_header = request.headers.get("range")

    def iter_file(start: int, end: int):
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk: break
                remaining -= len(chunk)
                yield chunk

    if range_header:
        try:
            ranges = range_header.replace("bytes=", "").split("-")
            start = int(ranges[0])
            end = int(ranges[1]) if ranges[1] else file_size - 1
        except Exception:
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        return StreamingResponse(
            iter_file(start, end), status_code=206, media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes", "Content-Length": str(chunk_size),
            }
        )
    
    return StreamingResponse(
        iter_file(0, file_size - 1), status_code=200, media_type=content_type,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)}
    )

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str, name: str = "Аноним"):
    await manager.connect(ws, room_id)
    await manager.broadcast(room_id, {
        "type": "chat", "name": "Система", "text": f"{name} вошёл в комнату"
    })

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "chat":
                text = str(data.get("text", ""))[:300]
                await manager.broadcast(room_id, {
                    "type": "chat", "name": name, "text": text
                }, exclude=ws)

            elif msg_type == "sync":
                await manager.broadcast(room_id, {
                    "type": "sync", "time": data.get("time", 0), "paused": data.get("paused", True)
                }, exclude=ws)

            elif msg_type == "track_change":
                idx = data.get("index", 0)
                if room_id in rooms and 0 <= idx < len(rooms[room_id]["playlist"]):
                    rooms[room_id]["current_index"] = idx
                    await manager.broadcast(room_id, {
                        "type": "playlist_update",
                        "playlist": rooms[room_id]["playlist"],
                        "current_index": idx
                    })

    except WebSocketDisconnect:
        manager.disconnect(ws, room_id)
        await manager.broadcast(room_id, {
            "type": "chat", "name": "Система", "text": f"{name} покинул комнату"
        })