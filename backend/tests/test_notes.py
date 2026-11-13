"""회의록 CRUD. 본문을 20자 미만으로 두어 Gemini 를 부르지 않는다 (구분은 test_classify.py)."""

SHORT_BODY = "짧은 메모"


def make_note(client, **overrides) -> dict:
    payload = {
        "title": "주간 기획 회의",
        "met_at": "2026-03-10T01:00:00Z",
        "attendees": "김대리, 이주임",
        "body": SHORT_BODY,
        **overrides,
    }
    response = client.post("/api/notes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# 매트릭스 1
def test_create_note_returns_201(client):
    note = make_note(client)
    assert note["id"] >= 1
    assert note["met_at"] == "2026-03-10T01:00:00Z"
    assert note["body"] == SHORT_BODY


# 매트릭스 2
def test_list_excludes_body(client):
    make_note(client)
    response = client.get("/api/notes")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert "body" not in items[0]


# 매트릭스 3
def test_get_single_includes_body(client):
    note = make_note(client)
    response = client.get(f"/api/notes/{note['id']}")
    assert response.status_code == 200
    assert response.json()["body"] == SHORT_BODY


# 매트릭스 8
def test_create_without_title_is_400(client):
    response = client.post("/api/notes", json={"met_at": "2026-03-10T01:00:00Z", "body": SHORT_BODY})
    assert response.status_code == 400


# 매트릭스 9
def test_create_with_bad_met_at_is_400(client):
    response = client.post("/api/notes", json={"title": "회의", "met_at": "어제 오후", "body": SHORT_BODY})
    assert response.status_code == 400


# 매트릭스 10
def test_unknown_id_is_404(client):
    assert client.get("/api/notes/9999").status_code == 404


# 매트릭스 11
def test_unknown_field_is_422(client):
    response = client.post(
        "/api/notes",
        json={"title": "회의", "met_at": "2026-03-10T01:00:00Z", "body": SHORT_BODY, "color": "red"},
    )
    assert response.status_code == 422


# 매트릭스 4
def test_update_all_fields_returns_200(client):
    note = make_note(client)
    payload = {
        "title": "바뀐 제목",
        "met_at": "2026-03-11T02:30:00Z",
        "attendees": "박과장",
        "body": "바뀐 메모",
        "summary": "요약 한 줄",
        "decisions": "결정 한 줄",
        "todos": "목록 화면 구현 | 김대리 | 다음 주 금요일",
    }
    response = client.put(f"/api/notes/{note['id']}", json=payload)
    assert response.status_code == 200
    updated = client.get(f"/api/notes/{note['id']}").json()
    assert {k: updated[k] for k in payload} == payload


def test_update_unknown_id_is_404(client):
    payload = {"title": "회의", "met_at": "2026-03-10T01:00:00Z", "body": SHORT_BODY}
    assert client.put("/api/notes/9999", json=payload).status_code == 404


# 매트릭스 5
def test_delete_returns_204(client):
    note = make_note(client)
    response = client.delete(f"/api/notes/{note['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/notes/{note['id']}").status_code == 404


def test_delete_unknown_id_is_404(client):
    assert client.delete("/api/notes/9999").status_code == 404
