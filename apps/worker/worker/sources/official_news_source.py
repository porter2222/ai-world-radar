from __future__ import annotations

from hashlib import sha256

from worker.collectors.hn_algolia import normalize_url
from worker.collectors.official_news import OfficialNewsEntry, OfficialSourceProfile
from worker.schemas.source import SourceCreate, SourceSignalCreate


def build_official_news_source(profile: OfficialSourceProfile) -> SourceCreate:
    """构造官方新闻来源配置。

    输入：官方来源 profile。
    输出：可交给 SignalService.upsert_source 的 SourceCreate。
    """
    return SourceCreate(
        source_key=profile.source_key,
        name=profile.name,
        source_type="official",
        fetch_method=profile.mode,
        entry_url=profile.entry_url,
        fetch_config={"mode": profile.mode, "entry_url": profile.entry_url},
    )


def official_news_entry_to_signal(entry: OfficialNewsEntry) -> SourceSignalCreate:
    """把 OfficialNewsEntry 映射成新版来源信号。

    输入：RSS、Atom 或 HTML collector 规范化后的官方新闻条目。
    输出：可交给 SignalService.upsert_signal 的 SourceSignalCreate。
    """
    profile = entry.profile
    return SourceSignalCreate(
        source_key=profile.source_key,
        source_item_id=entry.entry_id,
        original_title=entry.title,
        original_url=entry.url,
        canonical_url=normalize_url(entry.url),
        published_at=entry.published_at,
        language="en",
        raw_summary=entry.summary,
        source_hash=f"official_news:{profile.source_key}:{_stable_entry_hash(entry.entry_id)}",
        heat_metrics={"official_source": True},
        metadata={
            "source": "official_news",
            "profile_key": profile.source_key,
            "profile_name": profile.name,
            "mode": profile.mode,
            "entry_id": entry.entry_id,
        },
    )


def _stable_entry_hash(value: str) -> str:
    """生成官方条目的稳定短哈希。

    输入：entry id 或 URL。
    输出：16 位 sha256 十六进制前缀，避免 source_hash 过长。
    """
    return sha256(value.encode("utf-8")).hexdigest()[:16]
