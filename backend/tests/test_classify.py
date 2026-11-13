"""2.8 - 세 갈래 구분. 실제 Gemini 를 부른다 (대역 금지, docs/05-conventions.md)."""

import pytest
from google.genai import errors

import config
import gemini

MEETING_BODY = """2차 스프린트 회의입니다.
김대리: 목록 화면과 검색 기능은 제가 다음 주 금요일까지 만들겠습니다.
이주임: 받아쓰기 오류 처리는 제가 이번 주 안에 끝낼게요.
박과장: 좋습니다. 그럼 출시일은 4월 1일로 확정하겠습니다. 모두 동의하시죠?
김대리, 이주임: 네, 동의합니다.
박과장: 디자인 색상은 파란색과 초록색 중에 고민인데 다음에 다시 이야기해 봅시다.
이주임: 그런데 어제 점심 김치찌개 정말 맛있었어요."""

NOT_MEETING_BODY = """김치찌개 끓이는 법: 냄비에 돼지고기와 김치를 넣고 볶는다.
물을 붓고 20분 끓인 뒤 두부와 대파를 넣고 5분 더 끓인다."""


def post_note(client, body: str) -> dict:
    response = client.post(
        "/api/notes",
        json={"title": "2차 스프린트", "met_at": "2026-03-10T01:00:00Z", "attendees": "김대리, 이주임, 박과장", "body": body},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_meeting_body_is_split_into_three(client, gemini_pause):
    note = post_note(client, MEETING_BODY)

    summary_lines = note["summary"].splitlines()
    assert 1 <= len(summary_lines) <= 5

    # 합의가 끝난 것만 결정사항에 들어간다
    assert "4월 1일" in note["decisions"]
    assert "파란색" not in note["decisions"]

    # 할 일은 한 줄에 하나씩, 내용 | 담당자 | 기한
    todo_lines = note["todos"].splitlines()
    assert len(todo_lines) >= 2
    for line in todo_lines:
        assert len(line.split(" | ")) == 3, line
    assert any("김대리" in line and "다음 주 금요일" in line for line in todo_lines)

    # 잡담은 버린다
    assert "김치찌개" not in note["summary"] + note["decisions"] + note["todos"]


# 매트릭스 14
def test_not_meeting_body_leaves_three_empty(client, gemini_pause):
    note = post_note(client, NOT_MEETING_BODY)
    assert (note["summary"], note["decisions"], note["todos"]) == ("", "", "")


def test_short_body_skips_classification(client):
    note = post_note(client, "열아홉 글자 짜리 짧은 메모입니다")
    assert len(note["body"]) < config.MIN_CLASSIFY_CHARS
    assert (note["summary"], note["decisions"], note["todos"]) == ("", "", "")


def test_gemini_failure_still_saves_with_empty_three(client, gemini_pause, monkeypatch, caplog):
    # 없는 모델 이름으로 실제 Gemini 를 불러 실패를 만든다
    monkeypatch.setattr(config, "GEMINI_MODEL", "no-such-model-for-test")
    note = post_note(client, MEETING_BODY)
    assert (note["summary"], note["decisions"], note["todos"]) == ("", "", "")
    assert "세 갈래 구분 실패" in caplog.text


@pytest.mark.parametrize("status_code", [429, 503])
def test_retries_once_on_429_and_503(status_code, monkeypatch):
    monkeypatch.setattr(gemini, "RETRY_DELAY_SECONDS", 0)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise errors.APIError(status_code, {"error": {"message": "busy"}})
        return "ok"

    assert gemini.call_with_retry(flaky) == "ok"
    assert len(calls) == 2


def test_does_not_retry_twice(monkeypatch):
    monkeypatch.setattr(gemini, "RETRY_DELAY_SECONDS", 0)
    calls = []

    def always_busy():
        calls.append(1)
        raise errors.APIError(429, {"error": {"message": "busy"}})

    with pytest.raises(errors.APIError):
        gemini.call_with_retry(always_busy)
    assert len(calls) == 2


def test_prompt_contains_spec_criteria():
    for criterion in (
        "요약 - 회의 전체를 3~5줄로. 새로운 사실을 지어내지 말 것",
        "결정사항 - 「하기로 했다 / 확정 / 승인」 처럼 합의가 끝난 것만. 논의만 하고 안 정한 것은 넣지 말 것",
        "할 일 - 담당자와 기한이 드러난 것만. 담당자가 없으면 미정으로 적을 것",
        "셋 중 어디에도 안 들어가는 잡담은 버릴 것",
    ):
        assert criterion in gemini.CLASSIFY_PROMPT
