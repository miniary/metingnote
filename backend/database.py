"""SQLite 연결과 세션."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_PATH

engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    # FastAPI 는 요청을 여러 스레드에서 처리한다
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # 모델을 등록한 뒤 테이블을 만든다
    import models  # noqa: F401

    Base.metadata.create_all(engine)
