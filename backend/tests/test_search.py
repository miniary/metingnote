"""2.7 - 검색. q 는 제목 · 참석자 부분 일치, from · to 는 로컬 날짜로 양끝 포함."""

from tests.test_notes import make_note

KST_OFFSET = -540  # JS getTimezoneOffset() 값 (한국)


def titles(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["title"] for item in response.json()}


# 매트릭스 6
def test_q_matches_title_and_attendees_only(client):
    make_note(client, title="신규 기획 회의", attendees="김대리")
    make_note(client, title="주간 회의", attendees="기획팀 박과장")
    make_note(client, title="예산 회의", attendees="이주임", body="기획 이야기")

    assert titles(client.get("/api/notes", params={"q": "기획"})) == {"신규 기획 회의", "주간 회의"}


def test_from_to_include_both_ends(client):
    make_note(client, title="3월 9일", met_at="2026-03-09T03:00:00Z")
    make_note(client, title="3월 10일", met_at="2026-03-10T03:00:00Z")
    make_note(client, title="3월 11일 밤", met_at="2026-03-11T23:59:59Z")
    make_note(client, title="3월 12일", met_at="2026-03-12T00:00:00Z")

    response = client.get("/api/notes", params={"from": "2026-03-10", "to": "2026-03-11"})
    assert titles(response) == {"3월 10일", "3월 11일 밤"}


def test_from_to_use_local_date(client):
    # UTC 3월 10일 15:30 = 한국 3월 11일 00:30
    make_note(client, title="자정 넘은 회의", met_at="2026-03-10T15:30:00Z")

    kst = {"from": "2026-03-11", "to": "2026-03-11", "tz_offset": KST_OFFSET}
    assert titles(client.get("/api/notes", params=kst)) == {"자정 넘은 회의"}

    kst_prev_day = {"from": "2026-03-10", "to": "2026-03-10", "tz_offset": KST_OFFSET}
    assert titles(client.get("/api/notes", params=kst_prev_day)) == set()


def test_bad_date_format_is_400(client):
    assert client.get("/api/notes", params={"from": "3월 10일"}).status_code == 400


def test_q_treats_percent_as_text(client):
    make_note(client, title="달성률 100% 점검")
    make_note(client, title="주간 회의")
    assert titles(client.get("/api/notes", params={"q": "%"})) == {"달성률 100% 점검"}
