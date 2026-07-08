from fastapi import FastAPI
from app.routes import router

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Подключаем роутер с нашими эндпоинтами
app.include_router(router)