import os
import re
import shutil
import json
import difflib
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import Base, engine, get_db
import models
from manager import manager

Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- КОНФИГУРАЦИЯ БЕЗОПАСНОСТИ АДМИНКИ ---
ADMIN_PASSWORD = "strongpasswordsasha" 

MEDIA_DIR = Path("media")
COVERS_DIR = MEDIA_DIR / "covers"
VIDEOS_DIR = MEDIA_DIR / "videos"
COVERS_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

# Мониторим статику
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

ROOMS = {}

def extract_youtube_id(url: str) -> str:
    pattern = r'(?:https?://)?(?:www\.)?(?:youtube\.com/(?:[^/\ns]+/\S+/|(?:v|e(?:mbed)?)/|\S*?[?&]v=)|youtu\.be/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else url

# --- ПРОВЕРКА ПАРОЛЯ АДМИНА ---
def verify_admin(x_admin_password: str = Header(None)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Неверный пароль админа")

# --- РОУТЫ СТРАНИЦ ---

# Изменили: теперь главная страница редиректит на случайную комнату, чтобы предотвратить баг с общей сессией
from fastapi.responses import RedirectResponse
import uuid

@app.get("/")
async def root_redirect():
    random_room = str(uuid.uuid4())[:8]  # Короткий красивый ID комнаты
    return RedirectResponse(url=f"/room/{random_room}")

@app.get("/room/{room_id}", response_class=HTMLResponse)
async def get_room_page(room_id: str):
    # Отдаем index.html. Браузер прочитает pathname на фронте и поймет ID комнаты
    html_path = Path("static/index.html")
    if not html_path.exists():
        return HTMLResponse("Файл static/index.html не найден", status_code=404)
    return html_path.read_text(encoding="utf-8")

@app.get("/admin", response_class=HTMLResponse)
async def get_admin_page():
    return Path("static/admin.html").read_text(encoding="utf-8")

# Проверка пароля со стороны фронтенда при входе
@app.post("/api/admin/verify")
async def verify_password_route(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        return {"status": "success"}
    return JSONResponse({"status": "error", "message": "Неверный пароль!"}, status_code=401)


# --- API АДМИНКИ (ЗАЩИЩЕНО ХЕДЕРОМ) ---

@app.post("/api/admin/upload-video", dependencies=[Depends(verify_admin)])
async def upload_local_video(file: UploadFile = File(...)):
    file_path = VIDEOS_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"url": f"/media/videos/{file.filename}", "name": file.filename}

@app.post("/api/admin/presets", dependencies=[Depends(verify_admin)])
async def save_preset(
    preset_id: str = Form(None),
    title: str = Form(...),
    description: str = Form(""),
    preset_type: str = Form("movie"),
    episodes_json: str = Form(...),
    cover: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    db_preset = None
    if preset_id and preset_id.isdigit():
        db_preset = db.query(models.Preset).filter(models.Preset.id == int(preset_id)).first()

    if db_preset:
        db_preset.title = title
        db_preset.description = description
        db_preset.preset_type = preset_type
    else:
        db_preset = models.Preset(title=title, description=description, preset_type=preset_type)
        db.add(db_preset)
        db.commit()
        db.refresh(db_preset)

    if cover:
        file_path = COVERS_DIR / cover.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(cover.file, buffer)
        db_preset.cover = f"/media/covers/{cover.filename}"
    elif not db_preset.cover:
        db_preset.cover = "/static/no-cover.png"

    db.query(models.Episode).filter(models.Episode.preset_id == db_preset.id).delete()

    try:
        episodes_data = json.loads(episodes_json)
        for idx, ep in enumerate(episodes_data):
            src_val = extract_youtube_id(ep["src"]) if ep["type"] == "youtube" else ep["src"]
            db_episode = models.Episode(
                preset_id=db_preset.id, name=ep["name"], video_type=ep["type"], src=src_val, order=idx
            )
            db.add(db_episode)
        db.commit()
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)

    return {"status": "success", "preset_id": db_preset.id}

# --- ПУБЛИЧНЫЙ API И КЛИЕНТСКИЙ WEBSOCKET ---

@app.get("/api/presets")
async def list_presets(q: str = "", db: Session = Depends(get_db)):
    presets = db.query(models.Preset).all()
    if q:
        q = q.lower().strip()
        scored_presets = []
        for p in presets:
            title_lower = p.title.lower()
            desc_lower = p.description.lower() if p.description else ""
            if q in title_lower:
                score = 2.0 + (len(q) / len(title_lower))
            else:
                title_score = difflib.SequenceMatcher(None, q, title_lower).ratio()
                desc_score = difflib.SequenceMatcher(None, q, desc_lower).ratio() * 0.3
                score = max(title_score, desc_score)
            if score > 0.38 or q in title_lower:
                scored_presets.append((score, p))
        scored_presets.sort(key=lambda x: x[0], reverse=True)
        presets = [item[1] for item in scored_presets]

    result = []
    for p in presets:
        result.append({
            "id": p.id, "title": p.title, "description": p.description, "type": p.preset_type, "cover": p.cover,
            "episodes": [{"name": ep.name, "type": ep.video_type, "src": ep.src} for ep in sorted(p.episodes, key=lambda x: x.order)]
        })
    return result

@app.get("/room-info/{room_id}")
async def get_room_info(room_id: str):
    return ROOMS.get(room_id, {"playlist": [], "current_index": 0})

@app.post("/api/room/{room_id}/add-content")
async def add_content(room_id: str, body: dict):
    if room_id not in ROOMS:
        ROOMS[room_id] = {"playlist": [], "current_index": 0}
    raw_items = body.get("items", [])
    for item in raw_items:
        src = item.get("src", "")
        if item.get("type") == "youtube":
            src = extract_youtube_id(src)
        ROOMS[room_id]["playlist"].append({
            "type": item.get("type", "link"), "name": item.get("name", "Видео"), "src": src
        })
    await manager.broadcast(room_id, {
        "type": "playlist_update", "playlist": ROOMS[room_id]["playlist"], "current_index": ROOMS[room_id]["current_index"]
    })
    return {"status": "success"}

@app.delete("/api/room/{room_id}/remove/{index}")
async def remove_content(room_id: str, index: int):
    if room_id in ROOMS and index < len(ROOMS[room_id]["playlist"]):
        playlist = ROOMS[room_id]["playlist"]
        playlist.pop(index)
        curr = ROOMS[room_id]["current_index"]
        if curr >= len(playlist) and len(playlist) > 0:
            ROOMS[room_id]["current_index"] = len(playlist) - 1
        elif curr > index:
            ROOMS[room_id]["current_index"] -= 1
        await manager.broadcast(room_id, {
            "type": "playlist_update", "playlist": ROOMS[room_id]["playlist"], "current_index": ROOMS[room_id]["current_index"]
        })
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Не найдено")

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    room_id: str, 
    name: str = "Аноним", 
    user_id: str = None
):
    user_id = await manager.connect(websocket, room_id, name, user_id)
    
    # Инициализируем плейлист комнаты в памяти бэкеда, если её ещё нет
    if room_id not in ROOMS:
        ROOMS[room_id] = {"playlist": [], "current_index": 0}
        
    # Сразу при входе отправляем пользователю актуальный плейлист ЭТОЙ комнаты
    await websocket.send_json({
        "type": "playlist_update", 
        "playlist": ROOMS[room_id]["playlist"], 
        "current_index": ROOMS[room_id]["current_index"]
    })
    
    # Рассылаем всем обновленный список участников
    await manager.broadcast(
        room_id, 
        {"type": "room_users", "users": manager.get_room_users(room_id)}
    )
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "chat":
                await manager.broadcast(room_id, {"type": "chat", "name": name, "text": data.get("text")}, exclude_user_id=user_id)
            elif msg_type in ["sync", "playlist_update"]:
                await manager.broadcast(room_id, data, exclude_user_id=user_id)
            
            # Изменили: теперь состояние индекса трека обновляется в ROOMS на бэкенде
            elif msg_type == "track_change":
                new_idx = data.get("index", 0)
                ROOMS[room_id]["current_index"] = new_idx
                # Рассылаем обновление плейлиста всем в комнате, включая выбравшего трек
                await manager.broadcast(room_id, {
                    "type": "playlist_update", 
                    "playlist": ROOMS[room_id]["playlist"], 
                    "current_index": ROOMS[room_id]["current_index"]
                })
                
            elif msg_type in ["webrtc_offer", "webrtc_answer", "webrtc_candidate"]:
                target_id = data.get("target_id")
                data["sender_id"] = user_id
                await manager.send_to_user(room_id, target_id, data)

    except WebSocketDisconnect:
        manager.disconnect(room_id, user_id)
        
        await manager.broadcast(
            room_id, 
            {"type": "room_users", "users": manager.get_room_users(room_id)}
        )
        await manager.broadcast(
            room_id, 
            {"type": "webrtc_user_disconnected", "user_id": user_id}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)