"""Gemini 호출. 클라이언트는 모듈에 한 번 만들어 재사용한다 (docs/05-conventions.md)."""

import io
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

import config

logger = logging.getLogger(__name__)

client = genai.Client(api_key=config.get_gemini_api_key())

# SDK 는 내부에서 httpx2 로 통신한다. 승인 목록 밖이라 직접 import 하지 않고 SDK 가 쓰는 클래스를 가져온다
TRANSPORT_ERRORS = (httpx.HTTPError, errors.httpx2.HTTPError)

RETRYABLE_STATUS_CODES = {429, 503}
RETRY_DELAY_SECONDS = 2.0

T = TypeVar("T")


def call_with_retry(call: Callable[[], T]) -> T:
    """429 · 503 이면 잠시 뒤 1번만 다시 부른다."""
    try:
        return call()
    except errors.APIError as exc:
        if exc.code not in RETRYABLE_STATUS_CODES:
            raise
        logger.warning("Gemini %s - %s초 뒤 1번 다시 부릅니다", exc.code, RETRY_DELAY_SECONDS)
        time.sleep(RETRY_DELAY_SECONDS)
        return call()


# ---------- 세 갈래 구분 ----------

# 구분 기준은 docs/02-specs.md 2장 문구 그대로 넣는다
CLASSIFY_PROMPT = """아래는 회의 본문입니다. 요약 / 결정사항 / 할 일 세 갈래로 나누세요.

나누는 기준:
- 요약 - 회의 전체를 3~5줄로. 새로운 사실을 지어내지 말 것
- 결정사항 - 「하기로 했다 / 확정 / 승인」 처럼 합의가 끝난 것만. 논의만 하고 안 정한 것은 넣지 말 것
- 할 일 - 담당자와 기한이 드러난 것만. 담당자가 없으면 미정으로 적을 것
- 셋 중 어디에도 안 들어가는 잡담은 버릴 것

출력 규칙:
- is_meeting 에 본문이 회의 내용인지 먼저 적을 것. 회의 내용이 아니면 false 로 두고 세 갈래 모두 빈 배열로 둘 것
- summary 는 한 줄에 하나씩 3~5개 문장의 배열
- decisions 는 결정사항 하나당 한 항목
- todos 는 할 일 하나당 what(내용) · who(담당자) · when(기한). 기한은 회의에서 말한 그대로 적고 날짜로 바꾸지 말 것

--- 회의 본문 ---
"""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "is_meeting": {"type": "boolean"},
        "summary": {"type": "array", "items": {"type": "string"}},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "todos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "what": {"type": "string"},
                    "who": {"type": "string"},
                    "when": {"type": "string"},
                },
                "required": ["what", "who", "when"],
            },
        },
    },
    "required": ["is_meeting", "summary", "decisions", "todos"],
}



class _TodoOut(BaseModel):
    what: str
    who: str = ""
    when: str = ""


class _ClassifyOut(BaseModel):
    is_meeting: bool
    summary: list[str]
    decisions: list[str]
    todos: list[_TodoOut]


@dataclass(frozen=True)
class Classification:
    """DB 에 그대로 넣는 형태. 각 칸은 줄바꿈으로 항목을 구분한다."""

    summary: str = ""
    decisions: str = ""
    todos: str = ""


EMPTY_CLASSIFICATION = Classification()


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _todo_part(text: str) -> str:
    # 세로줄은 todos 저장 형식의 구분자라 내용 안에서는 바꿔 둔다
    return _one_line(text).replace("|", "/")


def _to_classification(parsed: _ClassifyOut) -> Classification:
    summary = [_one_line(line) for line in parsed.summary if line.strip()]
    decisions = [_one_line(line) for line in parsed.decisions if line.strip()]
    todos = [
        " | ".join(
            [_todo_part(todo.what), _todo_part(todo.who) or config.UNASSIGNED, _todo_part(todo.when)]
        )
        for todo in parsed.todos
        if todo.what.strip()
    ]
    return Classification("\n".join(summary), "\n".join(decisions), "\n".join(todos))


def classify_body(body: str) -> Classification:
    """본문을 세 갈래로 나눈다. 짧거나 실패하면 세 칸을 빈 값으로 돌려준다 (저장은 그대로 한다)."""
    if len(body.strip()) < config.MIN_CLASSIFY_CHARS:
        return EMPTY_CLASSIFICATION

    def call() -> types.GenerateContentResponse:
        return client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=CLASSIFY_PROMPT + body,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=CLASSIFY_SCHEMA,
            ),
        )

    try:
        response = call_with_retry(call)
        parsed = _ClassifyOut.model_validate(json.loads(response.text or ""))
    except (errors.APIError, *TRANSPORT_ERRORS, ValueError, ValidationError):
        # 화면에는 빈 세 칸으로 「구분 실패」가 보이고, 서버는 로그로만 남긴다
        logger.exception("세 갈래 구분 실패")
        return EMPTY_CLASSIFICATION

    if not parsed.is_meeting:
        logger.info("회의 내용이 아니어서 세 칸을 비웁니다")
        return EMPTY_CLASSIFICATION
    return _to_classification(parsed)


# ---------- 받아쓰기 ----------

TRANSCRIBE_PROMPT = """다음 회의 녹음을 받아쓰기 해 주세요.
- 들리는 그대로 원문 언어로 빠짐없이 적을 것. 요약하거나 내용을 바꾸지 말 것
- 알아들을 수 없는 부분은 [불명확] 으로 적을 것
- 받아쓴 글만 출력할 것"""

# 요청 전체 한도(20MB)보다 작게 잡는다. 이보다 크면 Files API 로 올린다
INLINE_AUDIO_LIMIT_BYTES = 15 * 1024 * 1024
FILE_POLL_SECONDS = 2.0


class TranscriptionError(Exception):
    """외부 호출(Gemini)로 받아쓰기를 하지 못했다."""


def _audio_part(data: bytes, mime_type: str) -> types.Part:
    if len(data) <= INLINE_AUDIO_LIMIT_BYTES:
        return types.Part.from_bytes(data=data, mime_type=mime_type)

    uploaded = call_with_retry(
        lambda: client.files.upload(file=io.BytesIO(data), config=types.UploadFileConfig(mime_type=mime_type))
    )
    while uploaded.state == types.FileState.PROCESSING:
        time.sleep(FILE_POLL_SECONDS)
        uploaded = call_with_retry(lambda: client.files.get(name=uploaded.name))
    if uploaded.state != types.FileState.ACTIVE:
        raise TranscriptionError(f"Gemini 가 오디오 파일을 처리하지 못했습니다: {uploaded.state}")
    return types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime_type)


def transcribe_audio(data: bytes, mime_type: str) -> str:
    """녹음을 받아 본문 텍스트로 돌려준다. 실패하면 TranscriptionError."""
    try:
        part = _audio_part(data, mime_type)
        response = call_with_retry(
            lambda: client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[part, TRANSCRIBE_PROMPT],
            )
        )
    except (errors.APIError, *TRANSPORT_ERRORS) as exc:
        raise TranscriptionError("Gemini 받아쓰기 호출 실패") from exc

    text = (response.text or "").strip()
    if not text:
        raise TranscriptionError("받아쓰기 결과가 비어 있습니다")
    return text
