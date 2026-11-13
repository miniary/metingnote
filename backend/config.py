"""환경 설정. 값은 프로젝트 루트의 .env 에서만 읽는다."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(PROJECT_DIR / ".env")

PORT = 8000

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# 테스트는 MEETINGNOTE_DB 로 다른 파일을 쓴다
DATABASE_PATH = Path(os.getenv("MEETINGNOTE_DB", BACKEND_DIR / "meetingnote.db"))

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav"}

# 이보다 짧은 본문은 세 갈래 구분을 부르지 않는다
MIN_CLASSIFY_CHARS = 20


def get_gemini_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY 가 없습니다. 프로젝트 루트의 .env 에 GEMINI_API_KEY=<키> 를 넣으세요."
        )
    return api_key


# 할 일에 담당자가 없을 때 적는 값
UNASSIGNED = "미정"
