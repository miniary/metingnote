"""MeetingNote 백엔드 진입점. 실행: uvicorn main:app --port 8000 (backend/ 에서)"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import gemini  # noqa: F401  키가 없으면 여기서 바로 알아보기 쉬운 오류로 멈춘다
from config import PROJECT_DIR
from database import init_db
from errors import register_error_handlers
from routes_notes import router as notes_router
from routes_todos import router as todos_router
from routes_upload import router as upload_router

# 화면 파일(index.html · app.js). 같은 오리진에서 제공해 CORS 가 필요 없다
FRONTEND_DIR = PROJECT_DIR / "frontend"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="MeetingNote", lifespan=lifespan)
register_error_handlers(app)
app.include_router(notes_router)
app.include_router(todos_router)
app.include_router(upload_router)
# /api 라우터 뒤에 붙인다. 앞에 두면 / 가 /api/* 요청까지 가로챈다
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
