from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base, PipelineRun, Source, SourceSignal
from worker.services.editorial_candidate_service import EditorialCandidateService


def make_session():
    """创建编辑筛选服务测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 `autoflush=False` 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def add_source(session, source_key: str = "hn_algolia") -> Source:
    """写入测试来源。

    输入：SQLAlchemy Session 和 source_key。
    输出：已 flush 且可被 SourceSignal 关联的 Source。
    """
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
    title: str,
    source_hash: str,
    original_url: str | None = None,
    canonical_url: str | None = None,
    pipeline_run_id: str | None = None,
    metadata: dict | None = None,
) -> SourceSignal:
    """写入测试 SourceSignal。

    输入：Session、Source、标题、URL、hash、可选 pipeline_run_id 和 metadata。
    输出：已 flush 的 SourceSignal。
    """
    signal = SourceSignal(
        source_id=source.id,
        pipeline_run_id=pipeline_run_id,
        original_title=title,
        original_url=original_url,
        canonical_url=canonical_url,
        source_hash=source_hash,
        heat_metrics={},
        metadata_json=metadata or {},
        collected_at=datetime.now(UTC),
    )
    session.add(signal)
    session.flush()
    return signal


def test_editorial_candidate_service_filters_invalid_and_processed_signals():
    """验证 selector 前硬过滤会排除无效和已处理信号。

    输入：有效信号、空标题信号、无 URL 信号、已有 pipeline_run_id 的信号。
    输出：只返回有效信号所在的 candidate group。
    """
    session = make_session()
    source = add_source(session)
    processed_run = PipelineRun(run_key="processed-run", trigger_type="manual", source_scope={})
    session.add(processed_run)
    session.flush()
    valid_signal = add_signal(
        session,
        source,
        title="OpenAI releases a new coding model",
        source_hash="hn:valid",
        original_url="https://news.ycombinator.com/item?id=1",
        canonical_url="https://openai.com/news/coding-model",
    )
    add_signal(
        session,
        source,
        title="",
        source_hash="hn:empty-title",
        original_url="https://example.com/empty-title",
    )
    add_signal(session, source, title="Missing traceable url", source_hash="hn:no-url")
    add_signal(
        session,
        source,
        title="Already processed signal",
        source_hash="hn:processed",
        original_url="https://example.com/processed",
        pipeline_run_id=processed_run.id,
    )

    groups = EditorialCandidateService(session).build_candidate_groups()

    assert len(groups) == 1
    assert groups[0].signal_ids == [valid_signal.id]


def test_editorial_candidate_service_filters_skipped_duplicate_trend_signals():
    """验证被 GitHub trend freshness gate 跳过的信号不会再次进入 selector。

    输入：一条 status=skipped_duplicate_trend 的 GitHub repo trend 信号。
    输出：候选 group 为空。
    """
    session = make_session()
    source = add_source(session, "github_repo_trends")
    skipped_signal = add_signal(
        session,
        source,
        title="Skipped repo trend",
        source_hash="github_repo_trends:example/repo:2026062608",
        original_url="https://github.com/example/repo",
        canonical_url="https://github.com/example/repo",
        metadata={"full_name": "example/repo"},
    )
    skipped_signal.status = "skipped_duplicate_trend"
    session.flush()

    groups = EditorialCandidateService(session).build_candidate_groups()

    assert groups == []


def test_editorial_candidate_service_filters_signals_outside_lookback_window():
    """验证超过 lookback 窗口的旧信号不会进入 selector。

    输入：一条当前信号和一条 published_at 超出 48 小时窗口的旧信号。
    输出：只返回当前信号所在的 candidate group。
    """
    session = make_session()
    source = add_source(session)
    now = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    fresh_signal = add_signal(
        session,
        source,
        title="Fresh AI event",
        source_hash="hn:fresh",
        original_url="https://example.com/fresh",
        canonical_url="https://example.com/fresh",
    )
    old_signal = add_signal(
        session,
        source,
        title="Old AI event",
        source_hash="hn:old",
        original_url="https://example.com/old",
        canonical_url="https://example.com/old",
    )
    fresh_signal.published_at = now - timedelta(hours=2)
    old_signal.published_at = now - timedelta(days=5)
    session.flush()

    groups = EditorialCandidateService(session).build_candidate_groups(now=now, lookback_hours=48)

    assert len(groups) == 1
    assert groups[0].signal_ids == [fresh_signal.id]


def test_editorial_candidate_service_merges_same_canonical_url():
    """验证相同 canonical_url 的多来源信号合并为一个 group。

    输入：两个 source_hash 不同但 canonical_url 相同的 SourceSignal。
    输出：一个 candidate group，包含两个 signal id。
    """
    session = make_session()
    source = add_source(session)
    first = add_signal(
        session,
        source,
        title="OpenAI announces a new developer agent",
        source_hash="hn:agent",
        original_url="https://news.ycombinator.com/item?id=2",
        canonical_url="https://openai.com/news/developer-agent",
    )
    second = add_signal(
        session,
        source,
        title="OpenAI developer agent release notes",
        source_hash="official:agent",
        original_url="https://openai.com/news/developer-agent?utm_source=rss",
        canonical_url="https://openai.com/news/developer-agent",
    )

    groups = EditorialCandidateService(session).build_candidate_groups()

    assert len(groups) == 1
    assert groups[0].signal_ids == [first.id, second.id]
    assert groups[0].merge_reason == "same_canonical_url"


def test_editorial_candidate_service_merges_same_github_repo():
    """验证同一 GitHub repo 的趋势和 release 信号合并。

    输入：canonical_url 不同但 metadata 都指向 `openai/codex` 的两个信号。
    输出：一个 candidate group，merge_reason 标记为 same_repo。
    """
    session = make_session()
    trend_source = add_source(session, "github_repo_trends")
    release_source = add_source(session, "github_releases")
    trend = add_signal(
        session,
        trend_source,
        title="openai/codex is gaining attention on GitHub",
        source_hash="github_repo_trends:openai/codex:2026062312",
        original_url="https://github.com/openai/codex",
        canonical_url="https://github.com/openai/codex",
        metadata={"full_name": "openai/codex"},
    )
    release = add_signal(
        session,
        release_source,
        title="openai/codex released v1.2.0",
        source_hash="github_releases:openai/codex:1",
        original_url="https://github.com/openai/codex/releases/tag/v1.2.0",
        canonical_url="https://github.com/openai/codex/releases/tag/v1.2.0",
        metadata={"owner": "openai", "repo": "codex"},
    )

    groups = EditorialCandidateService(session).build_candidate_groups()

    assert len(groups) == 1
    assert groups[0].signal_ids == [trend.id, release.id]
    assert groups[0].merge_reason == "same_repo"


def test_editorial_candidate_service_merges_similar_titles():
    """验证标题近似的不同 URL 信号可合并为一个 group。

    输入：URL 不同但标题高度相似的两个信号。
    输出：一个 candidate group，merge_reason 标记为 similar_title。
    """
    session = make_session()
    source = add_source(session)
    first = add_signal(
        session,
        source,
        title="Anthropic releases Claude Code for enterprise developers",
        source_hash="hn:claude-code",
        original_url="https://news.ycombinator.com/item?id=3",
        canonical_url="https://news.ycombinator.com/item?id=3",
    )
    second = add_signal(
        session,
        source,
        title="Anthropic releases Claude Code enterprise developer tools",
        source_hash="official:claude-code",
        original_url="https://www.anthropic.com/news/claude-code-enterprise",
        canonical_url="https://www.anthropic.com/news/claude-code-enterprise",
    )

    groups = EditorialCandidateService(session).build_candidate_groups()

    assert len(groups) == 1
    assert groups[0].signal_ids == [first.id, second.id]
    assert groups[0].merge_reason == "similar_title"
