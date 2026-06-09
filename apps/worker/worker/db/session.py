from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from worker.config import load_settings


def create_worker_engine(database_url: str | None = None, echo: bool = False) -> Engine:
    """创建 SQLAlchemy Engine。

    输入：可选 database_url 和 echo 开关；不传时读取 `.env`/默认配置。
    输出：SQLAlchemy `Engine`。
    """
    settings = load_settings()
    return create_engine(database_url or settings.database_url, echo=echo, future=True)


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """创建数据库 Session 工厂。

    输入：可选 database_url。
    输出：绑定 worker engine 的 `sessionmaker`。
    """
    return sessionmaker(bind=create_worker_engine(database_url), autoflush=False, expire_on_commit=False)


def session_scope(database_url: str | None = None) -> Generator[Session, None, None]:
    """提供带提交/回滚语义的 Session 上下文。

    输入：可选 database_url。
    输出：生成器形式的 `Session`；正常退出提交，异常时回滚。
    """
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
