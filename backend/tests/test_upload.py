"""2.10 - 녹취 업로드. 받아쓰기는 실제 Gemini 를 부른다."""

import asyncio
import io
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

import config
from routes_upload import read_limited

MEETING_WAV = Path(__file__).parent / "fixtures" / "meeting.wav"


def upload(client, name: str, data: bytes, content_type: str = "application/octet-stream"):
    return client.post("/api/upload", files={"file": (name, data, content_type)})


def test_real_wav_is_transcribed(client, gemini_pause):
    response = upload(client, "meeting.wav", MEETING_WAV.read_bytes(), "audio/wav")
    assert response.status_code == 200, response.text
    body = response.json()["body"]
    assert "스프린트" in body
    assert "금요일" in body


# 매트릭스 12
def test_mp4_is_415(client):
    assert upload(client, "meeting.mp4", b"not audio", "video/mp4").status_code == 415


# 매트릭스 13
def test_30mb_file_is_413(client):
    assert upload(client, "big.mp3", b"\0" * (30 * 1024 * 1024), "audio/mpeg").status_code == 413


def test_limit_boundary():
    # 한도와 같으면 통과, 1바이트라도 넘으면 413
    limit = 10
    assert asyncio.run(read_limited(UploadFile(io.BytesIO(b"x" * limit)), limit)) == b"x" * limit
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(read_limited(UploadFile(io.BytesIO(b"x" * (limit + 1))), limit))
    assert exc_info.value.status_code == 413


def test_gemini_failure_is_502(client, gemini_pause, monkeypatch):
    # 없는 모델 이름으로 실제 Gemini 를 불러 실패를 만든다
    monkeypatch.setattr(config, "GEMINI_MODEL", "no-such-model-for-test")
    response = upload(client, "meeting.wav", MEETING_WAV.read_bytes(), "audio/wav")
    assert response.status_code == 502
