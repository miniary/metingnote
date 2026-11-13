"""테스트 공통 설정. 테스트마다 빈 DB 파일을 쓴다."""

import os
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# main 을 불러오기 전에 테스트용 DB 경로를 정한다
_TEST_DB = BACKEND_DIR / "tests" / "test_meetingnote.db"
os.environ["MEETINGNOTE_DB"] = str(_TEST_DB)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import Base, engine  # noqa: E402

GEMINI_PAUSE_SECONDS = 1.0


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture()
def gemini_pause():
    """실제 Gemini 를 부르는 테스트는 요청 한도에 걸리지 않게 호출 사이를 띄운다."""
    time.sleep(GEMINI_PAUSE_SECONDS)
    yield
