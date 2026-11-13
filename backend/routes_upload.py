"""녹취 업로드 API - /api/upload. 파일을 받아 받아쓴 본문을 돌려준다 (저장은 하지 않는다)."""

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from config import ALLOWED_AUDIO_TYPES, MAX_UPLOAD_BYTES
from gemini import TranscriptionError, transcribe_audio
from schemas import UploadResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])

READ_CHUNK_BYTES = 1024 * 1024


async def read_limited(file: UploadFile, limit: int) -> bytes:
    """limit 를 넘으면 더 읽지 않고 413 을 낸다."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(READ_CHUNK_BYTES):
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail="파일이 25MB 를 넘습니다.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=UploadResult)
async def upload_audio(file: UploadFile = File(...)) -> UploadResult:
    suffix = Path(file.filename or "").suffix.lower()
    mime_type = ALLOWED_AUDIO_TYPES.get(suffix)
    if mime_type is None:
        raise HTTPException(status_code=415, detail="mp3 · wav 파일만 올릴 수 있습니다.")

    data = await read_limited(file, MAX_UPLOAD_BYTES)
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    try:
        body = transcribe_audio(data, mime_type)
    except TranscriptionError:
        logger.exception("받아쓰기 실패: %s", file.filename)
        raise HTTPException(status_code=502, detail="받아쓰기 서비스 호출에 실패했습니다.") from None

    return UploadResult(body=body)
