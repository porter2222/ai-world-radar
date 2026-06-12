from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from worker.schemas.common import WorkerSchema


class SourceCreate(WorkerSchema):
    """来源配置创建契约。

    输入：来源 key、名称、类型、抓取方式和抓取配置。
    输出：供 SignalService 幂等创建或更新 Source 的结构化 payload。
    """

    source_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=64)
    fetch_method: str = Field(min_length=1, max_length=64)
    entry_url: str | None = None
    enabled: bool = True
    default_weight: float = Field(default=1.0, ge=0)
    fetch_config: dict[str, Any] = Field(default_factory=dict)


class SourceSignalCreate(WorkerSchema):
    """来源信号创建契约。

    输入：来源 key、来源内 item ID、原始标题/URL、内容摘要、source_hash 和热度元数据。
    输出：供 SignalService 幂等写入 SourceSignal 的结构化 payload。
    """

    source_key: str = Field(min_length=1, max_length=64)
    source_item_id: str | None = Field(default=None, max_length=128)
    original_title: str = Field(min_length=1)
    original_url: str | None = None
    canonical_url: str | None = None
    published_at: datetime | None = None
    language: str | None = Field(default=None, max_length=32)
    raw_summary: str | None = None
    content_excerpt: str | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    content_cache_path: str | None = None
    source_hash: str = Field(min_length=1, max_length=255)
    heat_metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
