"""2.9 - 할 일 모아 보기. todos 는 PUT 으로 넣어 Gemini 를 부르지 않는다."""

from tests.test_notes import make_note


def put_todos(client, note: dict, todos: str) -> None:
    payload = {k: note[k] for k in ("title", "met_at", "attendees", "body")} | {
        "summary": "",
        "decisions": "",
        "todos": todos,
    }
    assert client.put(f"/api/notes/{note['id']}", json=payload).status_code == 200


# 매트릭스 7
def test_todos_fields_and_order(client):
    later = make_note(client, title="3월 회의", met_at="2026-03-20T01:00:00Z")
    earlier = make_note(client, title="2월 회의", met_at="2026-02-10T01:00:00Z")
    put_todos(client, later, "사용자 인터뷰 5건 | 박과장 | 다음 달 10일")
    put_todos(client, earlier, "목록 화면과 검색 기능 구현 | 김대리 | 다음 주 금요일\n받아쓰기 오류 처리 | 이주임 | 이번 주 안")

    response = client.get("/api/todos")
    assert response.status_code == 200
    todos = response.json()

    assert todos[0] == {
        "what": "목록 화면과 검색 기능 구현",
        "who": "김대리",
        "when": "다음 주 금요일",
        "note_id": earlier["id"],
        "note_title": "2월 회의",
    }
    # 회의 날짜 오래된 순
    assert [t["note_title"] for t in todos] == ["2월 회의", "2월 회의", "3월 회의"]


def test_todo_without_owner_is_unassigned(client):
    note = make_note(client)
    put_todos(client, note, "회의실 예약")
    assert client.get("/api/todos").json()[0]["who"] == "미정"


def test_no_todos_returns_empty_list(client):
    make_note(client)
    response = client.get("/api/todos")
    assert response.status_code == 200
    assert response.json() == []
