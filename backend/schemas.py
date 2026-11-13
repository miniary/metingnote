"""요청 · 응답 스키마. 스펙 외 필드는 extra="forbid" 로 막는다 (422)."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


def to_utc_naive(value: datetime) -> datetime:
    """DB 에는 시간대 없는 UTC 값으로 넣는다. 시간대가 없으면 이미 UTC 로 본다."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    met_at: datetime
    attendees: str = ""
    body: str = Field(min_length=1)

    @field_validator("met_at")
    @classmethod
    def _met_at_to_utc(cls, value: datetime) -> datetime:
        return to_utc_naive(value)


class NoteUpdate(NoteCreate):
    """PUT 은 전 필드를 받는다. 세 갈래 결과도 화면에서 고칠 수 있다."""

    summary: str = ""
    decisions: str = ""
    todos: str = ""


class NoteListItem(BaseModel):
    """목록 응답. body 는 넣지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    met_at: datetime
    attendees: str
    summary: str
    decisions: str
    todos: str

    @field_serializer("met_at")
    def _met_at_as_utc(self, value: datetime) -> str:
        # 화면이 로컬 시각으로 되돌릴 수 있게 UTC 표시(Z)를 붙여 보낸다
        return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


class NoteDetail(NoteListItem):
    """단건 응답. body 를 넣는다."""

    body: str


class TodoItem(BaseModel):
    what: str
    who: str
    when: str
    note_id: int
    note_title: str


class UploadResult(BaseModel):
    body: str
