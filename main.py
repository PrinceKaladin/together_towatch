import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

rooms: dict[str, dict] = {}

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Watch Together</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0f0f13;
    --surface: #1a1a22;
    --surface2: #22222e;
    --border: #2e2e3e;
    --accent: #7c6af7;
    --accent2: #5b52d6;
    --text: #e8e8f0;
    --muted: #6b6b82;
    --msg-bg: #1e1e2a;
    --radius: 12px;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  header {
    padding: 0 20px;
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    background: var(--surface);
  }

  .logo {
    font-size: 16px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text);
  }

  .logo-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
  }

  .room-info {
    font-size: 13px;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .viewers {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 13px;
    color: var(--muted);
  }

  .viewers-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #4caf77;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .main {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  .video-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 16px;
    gap: 12px;
  }

  .video-wrap {
    flex: 1;
    background: #000;
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    min-height: 0;
  }

  video {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: none;
  }

  video.loaded { display: block; }

  .upload-zone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 14px;
    color: var(--muted);
    cursor: pointer;
    width: 100%;
    height: 100%;
    transition: color 0.2s;
  }

  .upload-zone:hover { color: var(--accent); }

  .upload-zone svg {
    width: 48px;
    height: 48px;
    opacity: 0.5;
  }

  .upload-zone p { font-size: 15px; }
  .upload-zone span { font-size: 13px; opacity: 0.6; }

  .upload-btn {
    background: var(--accent);
    color: #fff;
    border: none;
    padding: 10px 22px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s, transform 0.1s;
  }

  .upload-btn:hover { background: var(--accent2); }
  .upload-btn:active { transform: scale(0.97); }

  #file-input { display: none; }

  .progress-bar {
    display: none;
    height: 3px;
    background: var(--border);
    border-radius: 99px;
    overflow: hidden;
  }

  .progress-bar.show { display: block; }
  .progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 99px;
    transition: width 0.2s;
    width: 0%;
  }

  .share-bar {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 14px;
    display: none;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    flex-shrink: 0;
  }

  .share-bar.show { display: flex; }

  .share-label { color: var(--muted); white-space: nowrap; }

  .share-url {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 7px 10px;
    font-size: 13px;
    color: var(--text);
    font-family: monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .copy-btn {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 7px 14px;
    border-radius: 7px;
    font-size: 13px;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s;
  }

  .copy-btn:hover { background: var(--border); }

  .chat-panel {
    width: 300px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    border-left: 1px solid var(--border);
    background: var(--surface);
  }

  .chat-header {
    padding: 14px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
    font-weight: 500;
    color: var(--muted);
    flex-shrink: 0;
  }

  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    scroll-behavior: smooth;
  }

  .chat-messages::-webkit-scrollbar { width: 4px; }
  .chat-messages::-webkit-scrollbar-track { background: transparent; }
  .chat-messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  .msg {
    background: var(--msg-bg);
    border-radius: 10px;
    padding: 8px 11px;
    font-size: 13.5px;
    line-height: 1.45;
    word-break: break-word;
    border: 1px solid var(--border);
  }

  .msg.system {
    background: transparent;
    border: none;
    text-align: center;
    color: var(--muted);
    font-size: 12px;
    padding: 2px 0;
  }

  .msg.own {
    background: #2a2060;
    border-color: #3d2e8a;
  }

  .msg-name {
    font-weight: 600;
    font-size: 11px;
    color: var(--accent);
    margin-bottom: 3px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .msg.own .msg-name { color: #9d8ff5; }

  .chat-input-wrap {
    padding: 12px;
    border-top: 1px solid var(--border);
    display: flex;
    gap: 8px;
    flex-shrink: 0;
  }

  .chat-input {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 9px 12px;
    font-size: 14px;
    color: var(--text);
    outline: none;
    transition: border-color 0.15s;
  }

  .chat-input:focus { border-color: var(--accent); }
  .chat-input::placeholder { color: var(--muted); }

  .send-btn {
    background: var(--accent);
    border: none;
    border-radius: 8px;
    color: #fff;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
    transition: background 0.15s;
  }

  .send-btn:hover { background: var(--accent2); }

  .name-modal {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    backdrop-filter: blur(4px);
  }

  .name-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 32px;
    width: 320px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .name-card h2 { font-size: 20px; font-weight: 600; }
  .name-card p { font-size: 14px; color: var(--muted); }

  .name-input {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 11px 14px;
    font-size: 15px;
    color: var(--text);
    outline: none;
    transition: border-color 0.15s;
    width: 100%;
  }

  .name-input:focus { border-color: var(--accent); }

  .name-btn {
    background: var(--accent);
    border: none;
    border-radius: 9px;
    padding: 12px;
    color: #fff;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
  }

  .name-btn:hover { background: var(--accent2); }

  @media (max-width: 700px) {
    .main { flex-direction: column; }

    .chat-panel {
      width: 100%;
      height: 240px;
      border-left: none;
      border-top: 1px solid var(--border);
    }

    .video-panel { padding: 10px; }
  }
</style>
</head>
<body>

<div class="name-modal" id="name-modal">
  <div class="name-card">
    <h2>Как вас зовут?</h2>
    <p>Это имя увидят все в комнате</p>
    <input class="name-input" id="name-input" placeholder="Ваше имя" maxlength="20" autofocus>
    <button class="name-btn" onclick="joinRoom()">Войти</button>
  </div>
</div>

<header>
  <div class="logo">
    <div class="logo-dot"></div>
    Watch Together
  </div>
  <div class="viewers">
    <div class="viewers-dot"></div>
    <span id="viewer-count">0 онлайн</span>
  </div>
</header>

<div class="main">
  <div class="video-panel">
    <div class="video-wrap" id="video-wrap">
      <div class="upload-zone" id="upload-zone" onclick="document.getElementById('file-input').click()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>
        </svg>
        <p>Загрузить видео</p>
        <span>MP4, WebM, MOV — до 2 ГБ</span>
        <button class="upload-btn" onclick="event.stopPropagation(); document.getElementById('file-input').click()">
          Выбрать файл
        </button>
      </div>
      <video id="video" controls preload="auto" playsinline></video>
    </div>

    <div class="progress-bar" id="progress-bar">
      <div class="progress-fill" id="progress-fill"></div>
    </div>

    <div class="share-bar" id="share-bar">
      <span class="share-label">Ссылка:</span>
      <div class="share-url" id="share-url"></div>
      <button class="copy-btn" onclick="copyLink()">Копировать</button>
    </div>

    <input type="file" id="file-input" accept="video/*" onchange="uploadVideo(this)">
  </div>

  <div class="chat-panel">
    <div class="chat-header">Чат</div>
    <div class="chat-messages" id="chat-messages"></div>
    <div class="chat-input-wrap">
      <input class="chat-input" id="chat-input" placeholder="Сообщение..." maxlength="300"
             onkeydown="if(event.key==='Enter') sendMessage()">
      <button class="send-btn" onclick="sendMessage()" aria-label="Отправить">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/>
        </svg>
      </button>
    </div>
  </div>
</div>

<script>
  const BASE = location.pathname.includes('/sasha-and-aziz') ? '/sasha-and-aziz' : '';
  const roomId = location.pathname.replace(BASE + '/room/', '').replace('/room/', '') || null;
  let myName = '';
  let ws = null;
  let isSyncing = false;
  const video = document.getElementById('video');

  function joinRoom() {
    const val = document.getElementById('name-input').value.trim();
    if (!val) return;
    myName = val;
    document.getElementById('name-modal').style.display = 'none';
    connectWS();
  }

  document.getElementById('name-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') joinRoom();
  });

  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${location.host}${BASE}/ws/${roomId || 'lobby'}?name=${encodeURIComponent(myName)}`;
    ws = new WebSocket(wsUrl);

    ws.onmessage = e => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'chat') addMsg(msg.name, msg.text, false);
      else if (msg.type === 'viewers') updateViewers(msg.count);
      else if (msg.type === 'sync') handleSync(msg);
      else if (msg.type === 'video_ready') loadVideo(msg.room_id, msg.filename);
    };

    ws.onerror = () => addSystemMsg('Ошибка подключения');
    ws.onclose = () => addSystemMsg('Отключено от сервера');
  }

  let videoReady = false;

  function handleSync(msg) {
    if (!videoReady) return;
    isSyncing = true;
    if (Math.abs(video.currentTime - msg.time) > 1.5) video.currentTime = msg.time;
    if (msg.paused && !video.paused) video.pause();
    else if (!msg.paused && video.paused) video.play().catch(() => {});
    setTimeout(() => { isSyncing = false; }, 300);
  }

  let chatFocused = false;
  document.getElementById('chat-input').addEventListener('focus', () => { chatFocused = true; });
  document.getElementById('chat-input').addEventListener('blur', () => {
    setTimeout(() => { chatFocused = false; }, 300);
  });

  video.addEventListener('play', () => {
    if (!isSyncing && ws?.readyState === 1)
      ws.send(JSON.stringify({ type: 'sync', paused: false, time: video.currentTime }));
  });

  video.addEventListener('pause', () => {
    if (isSyncing || chatFocused) return;
    if (ws?.readyState === 1)
      ws.send(JSON.stringify({ type: 'sync', paused: true, time: video.currentTime }));
  });

  video.addEventListener('seeked', () => {
    if (!isSyncing && ws?.readyState === 1)
      ws.send(JSON.stringify({ type: 'sync', paused: video.paused, time: video.currentTime }));
  });

  async function uploadVideo(input) {
    const file = input.files[0];
    if (!file) return;

    const bar = document.getElementById('progress-bar');
    const fill = document.getElementById('progress-fill');
    bar.classList.add('show');
    fill.style.width = '0%';

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/upload`);

    xhr.upload.onprogress = e => {
      if (e.lengthComputable) fill.style.width = (e.loaded / e.total * 100) + '%';
    };

    xhr.onload = () => {
      bar.classList.remove('show');
      if (xhr.status !== 200) {
        addSystemMsg('Ошибка загрузки: сервер вернул ' + xhr.status);
        return;
      }
      let data;
      try { data = JSON.parse(xhr.responseText); }
      catch(e) { addSystemMsg('Ошибка: неверный ответ сервера'); console.error(xhr.responseText); return; }
      if (!data.room_id || !data.filename) {
        addSystemMsg('Ошибка: сервер не вернул room_id');
        return;
      }
      const url = location.origin + BASE + '/room/' + data.room_id;
      document.getElementById('share-url').textContent = url;
      document.getElementById('share-bar').classList.add('show');
      loadVideo(data.room_id, data.filename);
      if (ws && ws.readyState === 1)
        ws.send(JSON.stringify({ type: 'video_ready', room_id: data.room_id, filename: data.filename }));
      history.pushState({}, '', BASE + '/room/' + data.room_id);
    };

    xhr.onerror = () => {
      document.getElementById('progress-bar').classList.remove('show');
      addSystemMsg('Ошибка сети при загрузке');
    };
    xhr.send(formData);
  }

  function loadVideo(room_id, filename) {
    const v = document.getElementById('video');
    const ext = filename.split('.').pop().toLowerCase();
    const mimeMap = { mp4: 'video/mp4', webm: 'video/webm', mov: 'video/mp4', mkv: 'video/webm' };
    const mime = mimeMap[ext] || 'video/mp4';
    const src = BASE + '/video/' + room_id + '/' + encodeURIComponent(filename);

    // Полностью пересоздаём source чтобы Chrome не кэшировал старый
    v.pause();
    v.removeAttribute('src');
    v.innerHTML = '';
    const source = document.createElement('source');
    source.src = src;
    source.type = mime;
    v.appendChild(source);
    v.load();
    v.classList.add('loaded');
    videoReady = true;

    v.onerror = () => {
      addSystemMsg('Ошибка загрузки видео: ' + (v.error ? v.error.message : 'неизвестно'));
      console.error('Video error:', v.error);
    };

    document.getElementById('upload-zone').style.display = 'none';
    const url = location.origin + BASE + '/room/' + room_id;
    document.getElementById('share-url').textContent = url;
    document.getElementById('share-bar').classList.add('show');
  }

  function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text || !ws) return;
    ws.send(JSON.stringify({ type: 'chat', text }));
    addMsg(myName, text, true);
    input.value = '';
  }

  function addMsg(name, text, own) {
    const box = document.getElementById('chat-messages');
    const d = document.createElement('div');
    d.className = 'msg' + (own ? ' own' : '');
    d.innerHTML = `<div class="msg-name">${escHtml(name)}</div>${escHtml(text)}`;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  }

  function addSystemMsg(text) {
    const box = document.getElementById('chat-messages');
    const d = document.createElement('div');
    d.className = 'msg system';
    d.textContent = text;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  }

  function updateViewers(count) {
    document.getElementById('viewer-count').textContent = count + ' онлайн';
  }

  function copyLink() {
    const url = document.getElementById('share-url').textContent;
    navigator.clipboard.writeText(url).then(() => {
      const btn = document.querySelector('.copy-btn');
      btn.textContent = 'Скопировано!';
      setTimeout(() => btn.textContent = 'Копировать', 2000);
    });
  }

  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  if (roomId && roomId !== 'lobby') {
    fetch(`${BASE}/room-info/${roomId}`).then(r => r.json()).then(data => {
      if (data.filename) loadVideo(roomId, data.filename);
    });
  }
</script>
</body>
</html>
"""


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
            self.rooms[room_id].discard(ws) if hasattr(self.rooms[room_id], 'discard') else None
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


def scan_uploads():
    """При старте подхватывает уже существующие папки в uploads/"""
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
            rooms[room_id] = {"filename": videos[0]}


scan_uploads()


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.get("/room/{room_id}", response_class=HTMLResponse)
async def room(room_id: str):
    return HTML


@app.get("/room-info/{room_id}")
async def room_info(room_id: str):
    if room_id in rooms:
        return JSONResponse(rooms[room_id])
    return JSONResponse({})


@app.get("/files")
async def list_files():
    """Список всех видео в папке uploads/ (для создания комнаты вручную)"""
    result = []
    for room_dir in UPLOAD_DIR.iterdir():
        if not room_dir.is_dir():
            continue
        for f in room_dir.iterdir():
            if f.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv", ".avi"):
                room_id = room_dir.name
                result.append({
                    "room_id": room_id,
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                    "has_room": room_id in rooms,
                })
    return JSONResponse(result)


@app.post("/create-room")
async def create_room(body: dict):
    """
    Создать комнату из файла который уже лежит в uploads/.

    Тело запроса:
      { "path": "uploads/myvideo.mp4" }
        — файл лежит прямо в uploads/, сервер переместит его в новую папку

      { "room_id": "abc123", "filename": "video.mp4" }
        — файл уже лежит в uploads/abc123/video.mp4, просто зарегистрировать комнату
    """
    # Вариант 1: файл уже в нужной папке uploads/<room_id>/<filename>
    room_id = body.get("room_id")
    filename = body.get("filename")
    if room_id and filename:
        path = UPLOAD_DIR / room_id / filename
        if not path.exists():
            return JSONResponse({"error": f"Файл не найден: {path}"}, status_code=404)
        rooms[room_id] = {"filename": filename}
        return JSONResponse({"room_id": room_id, "filename": filename})

    # Вариант 2: файл лежит прямо в uploads/ (или любом другом месте внутри uploads/)
    raw_path = body.get("path")
    if raw_path:
        src = Path(raw_path)
        if not src.is_absolute():
            src = Path(raw_path)  # относительный путь от cwd
        if not src.exists():
            return JSONResponse({"error": f"Файл не найден: {src}"}, status_code=404)

        new_room_id = str(uuid.uuid4())[:8]
        room_dir = UPLOAD_DIR / new_room_id
        room_dir.mkdir(exist_ok=True)
        dest = room_dir / src.name
        src.rename(dest)
        rooms[new_room_id] = {"filename": src.name}
        return JSONResponse({"room_id": new_room_id, "filename": src.name})

    return JSONResponse({"error": "Нужно передать либо {room_id, filename} либо {path}"}, status_code=400)


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    room_id = str(uuid.uuid4())[:8]
    room_dir = UPLOAD_DIR / room_id
    room_dir.mkdir(exist_ok=True)

    safe_name = Path(file.filename).name
    dest = room_dir / safe_name

    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    rooms[room_id] = {"filename": safe_name}
    return JSONResponse({"room_id": room_id, "filename": safe_name})


@app.get("/video/{room_id}/{filename}")
async def stream_video(room_id: str, filename: str, request: Request):
    path = UPLOAD_DIR / room_id / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)

    file_size = path.stat().st_size

    ext = path.suffix.lower()
    content_type = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
    }.get(ext, "video/mp4")

    range_header = request.headers.get("range")

    def iter_file(start: int, end: int):
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    if range_header:
        # Parse "bytes=start-end"
        try:
            ranges = range_header.replace("bytes=", "")
            start_str, end_str = ranges.split("-")
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
        except Exception:
            start = 0
            end = file_size - 1

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        return StreamingResponse(
            iter_file(start, end),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            }
        )
    else:
        return StreamingResponse(
            iter_file(0, file_size - 1),
            status_code=200,
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            }
        )


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str, name: str = "Аноним"):
    await manager.connect(ws, room_id)
    await manager.broadcast(room_id, {
        "type": "chat",
        "name": "Система",
        "text": f"{name} вошёл в комнату"
    })

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "chat":
                text = str(data.get("text", ""))[:300]
                await manager.broadcast(room_id, {
                    "type": "chat",
                    "name": name,
                    "text": text
                }, exclude=ws)

            elif msg_type == "sync":
                await manager.broadcast(room_id, {
                    "type": "sync",
                    "time": data.get("time", 0),
                    "paused": data.get("paused", True)
                }, exclude=ws)

            elif msg_type == "video_ready":
                r_id = data.get("room_id")
                fname = data.get("filename")
                if r_id and fname:
                    await manager.broadcast(room_id, {
                        "type": "video_ready",
                        "room_id": r_id,
                        "filename": fname
                    }, exclude=ws)

    except WebSocketDisconnect:
        manager.disconnect(ws, room_id)
        await manager.broadcast(room_id, {
            "type": "chat",
            "name": "Система",
            "text": f"{name} покинул комнату"
        })
