from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from scripts.cleanup_duplicate_github_trend_events import cleanup_duplicate_github_trend_events
from worker.models import (
    Base,
    EventCandidate,
    EventCandidateSignal,
    EventDossier,
    PublishedEvent,
    ReviewResult,
    Source,
    SourceSignal,
)


def make_session():
    """创建 cleanup 脚本测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 `autoflush=False` 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def add_source(session, source_key: str) -> Source:
    """写入或复用测试来源。

    输入：Session 和 source_key。
    输出：已 flush 的 Source。
    """
    existing = session.scalar(select(Source).where(Source.source_key == source_key))
    if existing is not None:
        return existing
    source = Source(
        source_key=source_key,
        name=source_key,
        source_type="test",
        fetch_method="fixture",
        fetch_config={},
    )
    session.add(source)
    session.flush()
    return source


def add_published_event_for_repo(
    session,
    *,
    repo_full_name: str,
    published_at: datetime,
    source_keys: list[str] | None = None,
) -> PublishedEvent:
    """写入一条测试用 PublishedEvent 及其来源信号链路。

    输入：repo 名、发布时间和支撑 source_keys。
    输出：已 flush 的 PublishedEvent。
    """
    source_keys = source_keys or ["github_repo_trends"]
    normalized_repo = repo_full_name.lower()
    source_key_suffix = "-".join(source_keys)
    candidate = EventCandidate(
        candidate_key=f"repo:{normalized_repo}:{published_at.strftime('%Y%m%d%H%M%S')}:{source_key_suffix}",
        title=f"{repo_full_name} gains attention",
        category="开源项目",
        heat_score=80,
        importance_score=60,
        audience_value_score=70,
        ranking_score=75,
        status="published",
        first_seen_at=published_at,
        last_seen_at=published_at,
    )
    session.add(candidate)
    session.flush()

    for index, source_key in enumerate(source_keys, start=1):
        source = add_source(session, source_key)
        signal = SourceSignal(
            source_id=source.id,
            source_item_id=repo_full_name,
            original_title=f"{repo_full_name} source {source_key}",
            original_url=f"https://github.com/{repo_full_name}",
            canonical_url=f"https://github.com/{repo_full_name}",
            source_hash=f"{source_key}:{normalized_repo}:{published_at.strftime('%Y%m%d%H%M%S')}:{index}",
            published_at=published_at,
            collected_at=published_at,
            heat_metrics={},
            metadata_json={"full_name": repo_full_name},
        )
        session.add(signal)
        session.flush()
        session.add(
            EventCandidateSignal(
                candidate_id=candidate.id,
                signal_id=signal.id,
                relation_type="primary",
                merge_confidence=1.0,
                merge_reason="test fixture",
            )
        )

    dossier = EventDossier(
        candidate_id=candidate.id,
        version=1,
        status="published_snapshot",
        card_title=f"{repo_full_name} gains attention",
        card_summary="测试用卡片摘要。",
        category="开源项目",
        signal_label="GitHub 热度",
        detail_title=f"{repo_full_name} gains attention",
        detail_summary="测试用详情摘要。",
        detail_body="测试正文第一段。\n\n测试正文第二段。",
        why_it_matters="测试用影响说明。",
        follow_up_points=[],
        source_refs=[{"title": repo_full_name, "url": f"https://github.com/{repo_full_name}", "source_key": source_keys[0]}],
    )
    session.add(dossier)
    session.flush()
    session.add(
        ReviewResult(
            dossier_id=dossier.id,
            candidate_id=candidate.id,
            decision="publish",
            risk_level="low",
            issues=[],
            revision_instructions="",
            checked_items={"source_supported": True},
        )
    )
    published = PublishedEvent(
        candidate_id=candidate.id,
        dossier_id=dossier.id,
        slug=candidate.candidate_key.replace(":", "-"),
        published_title=dossier.detail_title,
        published_card_summary=dossier.card_summary,
        published_detail_summary=dossier.detail_summary,
        published_detail_body=dossier.detail_body,
        category=dossier.category,
        signal_label=dossier.signal_label,
        source_refs=dossier.source_refs,
        ranking_score=candidate.ranking_score,
        status="published",
        published_at=published_at,
        created_at=published_at,
    )
    session.add(published)
    session.flush()
    return published


def test_find_duplicate_github_trend_events_dry_run_does_not_modify_database():
    """验证 dry-run 只报告同 repo 重复 trend，不修改数据库。

    输入：同一 repo 7 天内两条纯 github_repo_trends PublishedEvent。
    输出：summary 计划隐藏较旧事件，但两条事件状态仍为 published。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    older = add_published_event_for_repo(
        session,
        repo_full_name="NousResearch/hermes-agent",
        published_at=now - timedelta(days=3),
    )
    newer = add_published_event_for_repo(
        session,
        repo_full_name="NousResearch/hermes-agent",
        published_at=now - timedelta(hours=2),
    )

    summary = cleanup_duplicate_github_trend_events(session, apply=False, now=now)

    assert summary["mode"] == "dry_run"
    assert summary["duplicate_groups_count"] == 1
    assert summary["events_to_hide_count"] == 1
    assert summary["hidden_count"] == 0
    assert summary["events_to_hide"][0]["published_event_id"] == older.id
    assert session.get(PublishedEvent, older.id).status == "published"
    assert session.get(PublishedEvent, newer.id).status == "published"


def test_cleanup_duplicate_github_trend_events_apply_hides_older_duplicates():
    """验证 apply 会隐藏同 repo 7 天内较旧的重复 trend 发布事件。

    输入：同一 repo 7 天内两条纯 github_repo_trends PublishedEvent。
    输出：较旧事件变为 hidden_duplicate，较新事件保持 published。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    older = add_published_event_for_repo(
        session,
        repo_full_name="NousResearch/hermes-agent",
        published_at=now - timedelta(days=3),
    )
    newer = add_published_event_for_repo(
        session,
        repo_full_name="NousResearch/hermes-agent",
        published_at=now - timedelta(hours=2),
    )

    summary = cleanup_duplicate_github_trend_events(session, apply=True, now=now)

    assert summary["mode"] == "apply"
    assert summary["events_to_hide_count"] == 1
    assert summary["hidden_count"] == 1
    assert session.get(PublishedEvent, older.id).status == "hidden_duplicate"
    assert session.get(PublishedEvent, newer.id).status == "published"


def test_cleanup_duplicate_github_trend_events_ignores_non_trend_events():
    """验证非纯 github_repo_trends 事件不会被误隐藏。

    输入：同一 repo 的 github_releases 发布事件和一条 trend 事件。
    输出：cleanup 不认为它们是重复 trend group。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    release_event = add_published_event_for_repo(
        session,
        repo_full_name="openai/codex",
        published_at=now - timedelta(days=2),
        source_keys=["github_releases"],
    )
    trend_event = add_published_event_for_repo(
        session,
        repo_full_name="openai/codex",
        published_at=now - timedelta(hours=1),
        source_keys=["github_repo_trends"],
    )

    summary = cleanup_duplicate_github_trend_events(session, apply=True, now=now)

    assert summary["duplicate_groups_count"] == 0
    assert summary["events_to_hide_count"] == 0
    assert session.get(PublishedEvent, release_event.id).status == "published"
    assert session.get(PublishedEvent, trend_event.id).status == "published"


def test_cleanup_duplicate_github_trend_events_keeps_different_repos_separate():
    """验证不同 repo 的趋势事件不会互相影响。

    输入：两个不同 repo 各一条纯 github_repo_trends PublishedEvent。
    输出：cleanup 不隐藏任何事件。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    first = add_published_event_for_repo(
        session,
        repo_full_name="example/fast-llm",
        published_at=now - timedelta(days=1),
    )
    second = add_published_event_for_repo(
        session,
        repo_full_name="example/agent-kit",
        published_at=now - timedelta(hours=1),
    )

    summary = cleanup_duplicate_github_trend_events(session, apply=True, now=now)

    assert summary["duplicate_groups_count"] == 0
    assert summary["events_to_hide_count"] == 0
    assert session.get(PublishedEvent, first.id).status == "published"
    assert session.get(PublishedEvent, second.id).status == "published"
