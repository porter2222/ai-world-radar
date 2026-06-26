from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

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
from worker.services.editorial_candidate_service import EditorialCandidateGroup
from worker.services.github_trend_freshness_service import GitHubTrendFreshnessService


def make_session():
    """创建 GitHub trend freshness service 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 `autoflush=False` 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def add_source(session, source_key: str) -> Source:
    """写入测试来源。

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


def add_signal(
    session,
    source: Source,
    *,
    repo_full_name: str,
    source_hash: str,
    title: str = "GitHub repo trend signal",
    published_at: datetime | None = None,
    source_item_id: str | None = None,
    metadata: dict | None = None,
) -> SourceSignal:
    """写入指向某 GitHub repo 的测试 SourceSignal。

    输入：Session、Source、repo 名、source_hash、标题和可选时间/metadata。
    输出：已 flush 的 SourceSignal。
    """
    signal = SourceSignal(
        source_id=source.id,
        source_item_id=source_item_id or repo_full_name,
        original_title=title,
        original_url=f"https://github.com/{repo_full_name}",
        canonical_url=f"https://github.com/{repo_full_name}",
        source_hash=source_hash,
        published_at=published_at,
        collected_at=published_at or datetime(2026, 6, 26, 8, 0, tzinfo=UTC),
        heat_metrics={},
        metadata_json=metadata if metadata is not None else {"full_name": repo_full_name},
    )
    session.add(signal)
    session.flush()
    return signal


def add_published_event_for_repo(
    session,
    *,
    repo_full_name: str,
    published_at: datetime,
    source_keys: list[str] | None = None,
    status: str = "published",
) -> PublishedEvent:
    """写入一条带完整候选链路的已发布事件。

    输入：repo 名、发布时间、支撑信号 source_keys 和发布状态。
    输出：已 flush 的 PublishedEvent。
    """
    source_keys = source_keys or ["github_repo_trends"]
    normalized_repo = repo_full_name.lower()
    candidate = EventCandidate(
        candidate_key=f"repo:{normalized_repo}:{published_at.strftime('%Y%m%d%H%M%S')}:{'-'.join(source_keys)}",
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
        signal = add_signal(
            session,
            source,
            repo_full_name=repo_full_name,
            source_hash=f"{source_key}:{normalized_repo}:{published_at.strftime('%Y%m%d%H%M%S')}:{index}",
            title=f"{repo_full_name} source {source_key}",
            published_at=published_at,
        )
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
        source_refs=[
            {
                "title": f"{repo_full_name} on GitHub",
                "url": f"https://github.com/{repo_full_name}",
                "source_key": source_keys[0],
            }
        ],
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
        status=status,
        published_at=published_at,
        created_at=published_at,
    )
    session.add(published)
    session.flush()
    return published


def make_group(
    signal: SourceSignal,
    *,
    source_keys: list[str],
    repo_full_name: str | None = None,
) -> EditorialCandidateGroup:
    """构造 selector 前候选 group。

    输入：SourceSignal、source_keys 和可选 repo_full_name。
    输出：EditorialCandidateGroup。
    """
    return EditorialCandidateGroup(
        group_id="group_test",
        group_key=f"repo:{repo_full_name or signal.source_item_id}",
        title=signal.original_title,
        signal_ids=[signal.id],
        source_keys=source_keys,
        canonical_url=signal.canonical_url,
        repo_full_name=repo_full_name,
    )


def test_allows_first_seen_github_repo_trend_group():
    """验证首次出现的 GitHub repo trend 可以进入 selector。

    输入：无历史 PublishedEvent 的纯 github_repo_trends group。
    输出：decision.action 为 allow，reason 为 first_seen_repo。
    """
    session = make_session()
    source = add_source(session, "github_repo_trends")
    signal = add_signal(
        session,
        source,
        repo_full_name="example/fast-llm",
        source_hash="github_repo_trends:example/fast-llm:2026062608",
    )
    group = make_group(signal, source_keys=["github_repo_trends"], repo_full_name="example/fast-llm")

    decision = GitHubTrendFreshnessService(session).evaluate_group(
        group,
        now=datetime(2026, 6, 26, 8, 0, tzinfo=UTC),
    )

    assert decision.action == "allow"
    assert decision.reason == "first_seen_repo"
    assert decision.repo_full_name == "example/fast-llm"
    assert decision.matched_published_event_id is None


def test_skips_same_repo_pure_trend_when_published_within_cooldown():
    """验证 7 天内已发布同 repo 纯 trend 事件时，新 trend group 被跳过。

    输入：3 天前同 repo 纯 github_repo_trends PublishedEvent 和本轮同 repo trend signal。
    输出：decision.action 为 skip，并返回匹配到的 PublishedEvent ID。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    published = add_published_event_for_repo(
        session,
        repo_full_name="NousResearch/hermes-agent",
        published_at=now - timedelta(days=3),
    )
    source = add_source(session, "github_repo_trends")
    signal = add_signal(
        session,
        source,
        repo_full_name="NousResearch/hermes-agent",
        source_hash="github_repo_trends:nousresearch/hermes-agent:2026062608",
    )
    group = make_group(signal, source_keys=["github_repo_trends"], repo_full_name="nousresearch/hermes-agent")

    decision = GitHubTrendFreshnessService(session).evaluate_group(group, now=now)

    assert decision.action == "skip"
    assert decision.reason == "recently_published_repo_trend"
    assert decision.repo_full_name == "nousresearch/hermes-agent"
    assert decision.matched_published_event_id == published.id
    assert decision.cooldown_days == 7


def test_allows_same_repo_trend_after_cooldown_window():
    """验证超过 7 天冷却期后，同 repo trend 可以再次进入 selector。

    输入：8 天前同 repo 纯 trend PublishedEvent 和本轮同 repo trend signal。
    输出：decision.action 为 allow，reason 为 cooldown_expired。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    add_published_event_for_repo(
        session,
        repo_full_name="example/fast-llm",
        published_at=now - timedelta(days=8),
    )
    source = add_source(session, "github_repo_trends")
    signal = add_signal(
        session,
        source,
        repo_full_name="example/fast-llm",
        source_hash="github_repo_trends:example/fast-llm:2026062608",
    )
    group = make_group(signal, source_keys=["github_repo_trends"], repo_full_name="example/fast-llm")

    decision = GitHubTrendFreshnessService(session).evaluate_group(group, now=now)

    assert decision.action == "allow"
    assert decision.reason == "cooldown_expired"
    assert decision.matched_published_event_id is None


def test_allows_group_with_hard_freshness_source_even_when_repo_was_recently_published():
    """验证同 repo 有 GitHub Release / HN 等强新鲜度来源时不被纯趋势冷却期拦截。

    输入：3 天前同 repo trend 发布事件，本轮 group 同时包含 github_repo_trends 和 github_releases。
    输出：decision.action 为 allow，reason 为 has_hard_freshness_source。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    add_published_event_for_repo(
        session,
        repo_full_name="openai/codex",
        published_at=now - timedelta(days=3),
    )
    source = add_source(session, "github_repo_trends")
    signal = add_signal(
        session,
        source,
        repo_full_name="openai/codex",
        source_hash="github_repo_trends:openai/codex:2026062608",
    )
    group = make_group(signal, source_keys=["github_repo_trends", "github_releases"], repo_full_name="openai/codex")

    decision = GitHubTrendFreshnessService(session).evaluate_group(group, now=now)

    assert decision.action == "allow"
    assert decision.reason == "has_hard_freshness_source"
    assert decision.matched_published_event_id is None


def test_repo_matching_is_case_insensitive_and_can_use_source_item_id():
    """验证 repo 匹配大小写不敏感，并能从 SourceSignal.source_item_id 提取 repo。

    输入：历史事件 metadata 使用大写 repo；本轮信号 metadata 缺失 full_name，但 source_item_id 包含 repo。
    输出：decision.action 为 skip，repo_full_name 归一为小写。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    published = add_published_event_for_repo(
        session,
        repo_full_name="NousResearch/Hermes-Agent",
        published_at=now - timedelta(days=1),
    )
    source = add_source(session, "github_repo_trends")
    signal = add_signal(
        session,
        source,
        repo_full_name="unused/unused",
        source_hash="github_repo_trends:nousresearch/hermes-agent:2026062608",
        source_item_id="nousresearch/hermes-agent#2026062608",
        metadata={},
    )
    group = make_group(signal, source_keys=["github_repo_trends"], repo_full_name=None)

    decision = GitHubTrendFreshnessService(session).evaluate_group(group, now=now)

    assert decision.action == "skip"
    assert decision.repo_full_name == "nousresearch/hermes-agent"
    assert decision.matched_published_event_id == published.id


def test_mark_skipped_signals_records_status_and_metadata():
    """验证被跳过的 SourceSignal 会写入状态和可解释 metadata。

    输入：一个需要跳过的同 repo trend group。
    输出：signal.status 和 metadata_json.github_trend_freshness 均被更新。
    """
    session = make_session()
    now = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
    published = add_published_event_for_repo(
        session,
        repo_full_name="NousResearch/hermes-agent",
        published_at=now - timedelta(days=2),
    )
    source = add_source(session, "github_repo_trends")
    signal = add_signal(
        session,
        source,
        repo_full_name="NousResearch/hermes-agent",
        source_hash="github_repo_trends:nousresearch/hermes-agent:2026062608",
        metadata={"full_name": "NousResearch/hermes-agent", "existing": "kept"},
    )
    group = make_group(signal, source_keys=["github_repo_trends"], repo_full_name="nousresearch/hermes-agent")
    service = GitHubTrendFreshnessService(session)
    decision = service.evaluate_group(group, now=now)

    changed = service.mark_skipped_signals(group.signal_ids, decision, skipped_at=now)
    session.flush()
    saved_signal = session.scalars(select(SourceSignal).where(SourceSignal.id == signal.id)).one()
    freshness = saved_signal.metadata_json["github_trend_freshness"]

    assert changed == 1
    assert saved_signal.status == "skipped_duplicate_trend"
    assert saved_signal.metadata_json["existing"] == "kept"
    assert freshness["decision"] == "skip"
    assert freshness["reason"] == "recently_published_repo_trend"
    assert freshness["repo_full_name"] == "nousresearch/hermes-agent"
    assert freshness["matched_published_event_id"] == published.id
    assert freshness["cooldown_days"] == 7
    assert freshness["skipped_at"] == now.isoformat()
