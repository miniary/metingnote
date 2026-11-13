from datetime import datetime

from sqlalchemy import inspect, text

from database import SessionLocal, engine
from models import Meeting


def _make(title: str) -> Meeting:
    return Meeting(title=title, met_at=datetime(2026, 1, 1), body="본문")


def test_meeting_has_eight_fields_in_order(client):
    columns = [c["name"] for c in inspect(engine).get_columns("meetings")]
    assert columns == ["id", "title", "met_at", "attendees", "body", "summary", "decisions", "todos"]


def test_table_uses_autoincrement(client):
    with engine.connect() as conn:
        ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE name = 'meetings'")).scalar_one()
    assert "AUTOINCREMENT" in ddl


def test_deleted_id_is_not_reused(client):
    with SessionLocal() as db:
        first = _make("첫 회의")
        db.add(first)
        db.commit()
        deleted_id = first.id
        db.delete(first)
        db.commit()

        second = _make("둘째 회의")
        db.add(second)
        db.commit()
        assert second.id > deleted_id
