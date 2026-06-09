from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from worker.config import load_settings


def create_worker_engine(database_url: str | None = None, echo: bool = False) -> Engine:
    settings = load_settings()
    return create_engine(database_url or settings.database_url, echo=echo, future=True)


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_worker_engine(database_url), autoflush=False, expire_on_commit=False)


def session_scope(database_url: str | None = None) -> Generator[Session, None, None]:
    session_factory = create_session_factory(database_url)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
