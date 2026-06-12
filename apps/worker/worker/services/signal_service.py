from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.models import Source, SourceSignal
from worker.schemas.source import SourceCreate, SourceSignalCreate


class SignalService:
    """来源与信号写入服务。

    输入：SQLAlchemy Session。
    输出：提供 Source 和 SourceSignal 的幂等 upsert 能力。
    """

    def __init__(self, session: Session):
        """初始化服务。

        输入：外部传入且由调用方管理事务的 Session。
        输出：可复用的 SignalService 实例。
        """
        self.session = session

    def upsert_source(self, payload: SourceCreate) -> Source:
        """按 source_key 幂等写入来源。

        输入：SourceCreate payload。
        输出：已存在或新建并刷新后的 Source ORM 对象。
        """
        source = self.session.scalar(select(Source).where(Source.source_key == payload.source_key))
        if source is None:
            source = Source(source_key=payload.source_key)
            self.session.add(source)

        source.name = payload.name
        source.source_type = payload.source_type
        source.fetch_method = payload.fetch_method
        source.entry_url = payload.entry_url
        source.enabled = payload.enabled
        source.default_weight = payload.default_weight
        source.fetch_config = payload.fetch_config
        self.session.flush()
        return source

    def upsert_signal(self, payload: SourceSignalCreate) -> SourceSignal:
        """按来源和 source_hash 幂等写入信号。

        输入：SourceSignalCreate payload；其中 source_key 必须能找到已写入 Source。
        输出：已存在或新建并刷新后的 SourceSignal ORM 对象。
        """
        source = self.session.scalar(select(Source).where(Source.source_key == payload.source_key))
        if source is None:
            raise ValueError(f"Source not found for source_key={payload.source_key}")

        signal = self.session.scalar(
            select(SourceSignal).where(
                SourceSignal.source_id == source.id,
                SourceSignal.source_hash == payload.source_hash,
            )
        )
        if signal is None:
            signal = SourceSignal(source_id=source.id, source_hash=payload.source_hash)
            self.session.add(signal)

        signal.source_item_id = payload.source_item_id
        signal.original_title = payload.original_title
        signal.original_url = payload.original_url
        signal.canonical_url = payload.canonical_url
        signal.published_at = payload.published_at
        signal.language = payload.language
        signal.raw_summary = payload.raw_summary
        signal.content_excerpt = payload.content_excerpt
        signal.content_hash = payload.content_hash
        signal.content_cache_path = payload.content_cache_path
        signal.heat_metrics = payload.heat_metrics
        signal.metadata_json = payload.metadata
        self.session.flush()
        return signal
