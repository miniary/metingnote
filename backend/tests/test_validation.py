"""2.4 - 스키마와 예외 핸들러. 실제 API 경로로도 test_notes.py 에서 다시 확인한다."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from errors import register_error_handlers
from schemas import NoteCreate

probe_app = FastAPI()
register_error_handlers(probe_app)


@probe_app.post("/probe", status_code=201)
def probe(payload: NoteCreate) -> dict:
    return {"met_at": payload.met_at.isoformat()}


probe_client = TestClient(probe_app)

VALID = {"title": "주간 회의", "met_at": "2026-03-10T01:00:00Z", "body": "본문"}


def test_valid_payload_passes():
    assert probe_client.post("/probe", json=VALID).status_code == 201


def test_missing_required_field_is_400():
    for field in ("title", "met_at", "body"):
        payload = {k: v for k, v in VALID.items() if k != field}
        assert probe_client.post("/probe", json=payload).status_code == 400, field


def test_bad_met_at_is_400():
    assert probe_client.post("/probe", json={**VALID, "met_at": "어제"}).status_code == 400


def test_unknown_field_is_422():
    assert probe_client.post("/probe", json={**VALID, "color": "red"}).status_code == 422


def test_met_at_is_stored_as_utc():
    response = probe_client.post("/probe", json={**VALID, "met_at": "2026-03-10T10:00:00+09:00"})
    assert response.json()["met_at"] == "2026-03-10T01:00:00"
