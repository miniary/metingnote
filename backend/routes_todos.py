"""할 일 모아 보기 API - /api/todos"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import UNASSIGNED
from database import get_db
from models import Meeting
from schemas import TodoItem

router = APIRouter(prefix="/api/todos", tags=["todos"])

TODO_SEPARATOR = "|"


def parse_todo_line(line: str) -> tuple[str, str, str] | None:
    """「내용 | 담당자 | 기한」 한 줄을 나눈다. 기한은 말한 그대로 둔다."""
    parts = [part.strip() for part in line.split(TODO_SEPARATOR)]
    what = parts[0] if parts else ""
    if not what:
        return None
    who = parts[1] if len(parts) > 1 and parts[1] else UNASSIGNED
    when = TODO_SEPARATOR.join(parts[2:]).strip() if len(parts) > 2 else ""
    return what, who, when


@router.get("", response_model=list[TodoItem])
def list_todos(db: Session = Depends(get_db)) -> list[TodoItem]:
    # 회의 날짜 오래된 순. 기한으로 정렬하거나 거르지 않는다
    meetings = db.scalars(select(Meeting).order_by(Meeting.met_at.asc(), Meeting.id.asc()))
    items: list[TodoItem] = []
    for meeting in meetings:
        for line in meeting.todos.splitlines():
            parsed = parse_todo_line(line)
            if parsed is None:
                continue
            what, who, when = parsed
            items.append(TodoItem(what=what, who=who, when=when, note_id=meeting.id, note_title=meeting.title))
    return items
