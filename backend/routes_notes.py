"""회의록 API - /api/notes"""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database import get_db
from gemini import classify_body
from models import Meeting
from schemas import NoteCreate, NoteDetail, NoteListItem, NoteUpdate

router = APIRouter(prefix="/api/notes", tags=["notes"])


def get_meeting_or_404(db: Session, note_id: int) -> Meeting:
    meeting = db.get(Meeting, note_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return meeting


@router.post("", status_code=201, response_model=NoteDetail)
def create_note(payload: NoteCreate, db: Session = Depends(get_db)) -> Meeting:
    # 구분이 실패해도 저장은 그대로 한다 (세 칸은 빈 값)
    result = classify_body(payload.body)
    meeting = Meeting(
        **payload.model_dump(),
        summary=result.summary,
        decisions=result.decisions,
        todos=result.todos,
    )
    db.add(meeting)
    db.commit()
    return meeting


def local_day_start_in_utc(day: date, tz_offset: int) -> datetime:
    """로컬 날짜의 0시를 UTC 로 바꾼다. tz_offset 은 JS getTimezoneOffset() 값(분, UTC - 로컬)."""
    return datetime.combine(day, time.min) + timedelta(minutes=tz_offset)


@router.get("", response_model=list[NoteListItem])
def list_notes(
    q: str = "",
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    tz_offset: int = Query(default=0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> list[Meeting]:
    query = select(Meeting)

    keyword = q.strip()
    if keyword:
        # 제목과 참석자만 찾는다. 본문은 찾지 않는다
        # % · _ 를 글자 그대로 찾도록 이스케이프한다
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(Meeting.title.like(pattern, escape="\\"), Meeting.attendees.like(pattern, escape="\\"))
        )

    # from · to 는 양끝을 포함한다. to 는 그날 23:59:59 까지 = 다음 날 0시 전까지
    if date_from is not None:
        query = query.where(Meeting.met_at >= local_day_start_in_utc(date_from, tz_offset))
    if date_to is not None:
        next_day = date_to + timedelta(days=1)
        query = query.where(Meeting.met_at < local_day_start_in_utc(next_day, tz_offset))

    query = query.order_by(Meeting.met_at.desc(), Meeting.id.desc())
    return list(db.scalars(query))


@router.get("/{note_id}", response_model=NoteDetail)
def get_note(note_id: int, db: Session = Depends(get_db)) -> Meeting:
    return get_meeting_or_404(db, note_id)


@router.put("/{note_id}", response_model=NoteDetail)
def update_note(note_id: int, payload: NoteUpdate, db: Session = Depends(get_db)) -> Meeting:
    meeting = get_meeting_or_404(db, note_id)
    for field, value in payload.model_dump().items():
        setattr(meeting, field, value)
    db.commit()
    return meeting


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db)) -> Response:
    meeting = get_meeting_or_404(db, note_id)
    db.delete(meeting)
    db.commit()
    return Response(status_code=204)
