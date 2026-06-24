from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id(prefix: str) -> str:
    """生成带业务前缀的字符串主键。

    输入：业务前缀，例如 `sig`、`cand`、`dos`。
    输出：形如 `prefix_uuidhex` 的唯一 ID。
    """
    return f"{prefix}_{uuid.uuid4().hex}"


def utc_now() -> datetime:
    """Return the current wall-clock time as timezone-aware UTC."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """新版 P1-1 ORM declarative base。

    输入：无。
    输出：承载新版核心表 metadata 的 SQLAlchemy Base。
    """

    pass


class TimestampMixin:
    """通用时间戳字段 mixin。

    输入：无。
    输出：为继承模型提供 `created_at` 和 `updated_at` 字段。
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
