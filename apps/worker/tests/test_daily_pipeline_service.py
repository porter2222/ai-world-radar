from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base, PipelineRun, Source, SourceSignal
from worker.schemas.editorial_selection import (
    EditorialManualReviewItem,
    EditorialRejectedItem,
    EditorialSelectedItem,
    EditorialSelectionResult,
)
from worker.observability.run_logger import MemorySink, RunLogger
from worker.services.daily_pipeline_service import DailyPipelineConfig, DailyPipelineService


def make_session():
    """创建 DailyPipelineService 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 `autoflush=False` 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def add_source(session, source_key: str = "hn_algolia") -> Source:
    """写入测试来源。

    输入：SQLAlchemy Session 和 source_key。
    输出：已 flush 且可关联 SourceSignal 的 Source。
    """
    source = Source(source_key=source_key, name=source_key, source_type="test", fetch_method="fixture", fetch_config={})
    session.add(source)
    session.flush()
    return source


def add_signal(
    session,
    source: Source,
    *,
    title: str,
    source_hash: str,
    collected_at: datetime,
    original_url: str | None = None,
    canonical_url: str | None = None,
    pipeline_run_id: str | None = None,
) -> SourceSignal:
    """写入测试 SourceSignal。

    输入：Session、Source、标题、hash、采集时间、URL 和可选 pipeline_run_id。
    输出：已 flush 的 SourceSignal。
    """
    signal = SourceSignal(
        source_id=source.id,
        pipeline_run_id=pipeline_run_id,
        source_item_id=source_hash,
        original_title=title,
        original_url=original_url,
        canonical_url=canonical_url,
        source_hash=source_hash,
        collected_at=collected_at,
        heat_metrics={},
        metadata_json={},
    )
    session.add(signal)
    session.flush()
    return signal


class StaticSelectorAgent:
    """返回固定 selector 结果的测试 Agent。

    输入：预设 selected group id 列表；为空时按当前输入全选，可选 rejected/manual_review id 列表。
    输出：select 时按输入候选 group 生成 EditorialSelectionResult。
    """

    def __init__(
        self,
        *,
        selected_ids: list[str] | None = None,
        rejected_ids: list[str] | None = None,
        manual_review_ids: list[str] | None = None,
    ):
        """初始化测试 selector。

        输入：selected、rejected 和 manual_review 的 group id；selected_ids 为空时表示全选。
        输出：可记录输入并返回固定结构化结果的测试 Agent。
        """
        self.selected_ids = selected_ids
        self.rejected_ids = rejected_ids or []
        self.manual_review_ids = manual_review_ids or []
        self.calls = []

    def select(self, candidate_groups):
        """按预设 group id 返回 selector 结果。

        输入：candidate group dict 列表。
        输出：EditorialSelectionResult。
        """
        self.calls.append(candidate_groups)
        groups_by_id = {group["candidate_group_id"]: group for group in candidate_groups}
        selected_ids = self.selected_ids
        if selected_ids is None:
            skipped_ids = set(self.rejected_ids) | set(self.manual_review_ids)
            selected_ids = [group["candidate_group_id"] for group in candidate_groups if group["candidate_group_id"] not in skipped_ids]
        return EditorialSelectionResult(
            selected=[
                EditorialSelectedItem(
                    candidate_group_id=group_id,
                    signal_ids=groups_by_id[group_id]["signal_ids"],
                    event_title=groups_by_id[group_id]["title"],
                    priority_score=90,
                    suggested_angle="测试选题角度。",
                    reason="测试 selector 选中该候选。",
                )
                for group_id in selected_ids
                if group_id in groups_by_id
            ],
            rejected=[
                EditorialRejectedItem(candidate_group_id=group_id, reason="测试拒绝。")
                for group_id in self.rejected_ids
                if group_id in groups_by_id
            ],
            manual_review=[
                EditorialManualReviewItem(candidate_group_id=group_id, reason="测试人工复核。")
                for group_id in self.manual_review_ids
                if group_id in groups_by_id
            ],
        )


class OrderedDecisionSelectorAgent:
    """按输入顺序生成 selected/rejected/manual_review 的测试 Agent。

    输入：selected、rejected、manual_review 各自需要消费的数量。
    输出：select 时按候选 group 顺序切分并返回 EditorialSelectionResult。
    """

    def __init__(self, *, selected_count: int, rejected_count: int, manual_review_count: int):
        """初始化顺序决策 selector。

        输入：三类决策的数量。
        输出：可记录输入并按顺序分类的测试 Agent。
        """
        self.selected_count = selected_count
        self.rejected_count = rejected_count
        self.manual_review_count = manual_review_count
        self.calls = []

    def select(self, candidate_groups):
        """按输入顺序切分候选 group。

        输入：candidate group dict 列表。
        输出：包含 selected/rejected/manual_review 三类结果的 EditorialSelectionResult。
        """
        self.calls.append(candidate_groups)
        selected_groups = candidate_groups[: self.selected_count]
        rejected_start = self.selected_count
        rejected_end = rejected_start + self.rejected_count
        rejected_groups = candidate_groups[rejected_start:rejected_end]
        manual_review_groups = candidate_groups[rejected_end : rejected_end + self.manual_review_count]
        return EditorialSelectionResult(
            selected=[
                EditorialSelectedItem(
                    candidate_group_id=group["candidate_group_id"],
                    signal_ids=group["signal_ids"],
                    event_title=group["title"],
                    priority_score=90,
                    suggested_angle="测试选题角度。",
                    reason="测试 selector 选中该候选。",
                )
                for group in selected_groups
            ],
            rejected=[
                EditorialRejectedItem(candidate_group_id=group["candidate_group_id"], reason="测试拒绝。")
                for group in rejected_groups
            ],
            manual_review=[
                EditorialManualReviewItem(candidate_group_id=group["candidate_group_id"], reason="测试人工复核。")
                for group in manual_review_groups
            ],
        )


class RecordingPipelineRunner:
    """记录 pipeline 调用并创建测试 PipelineRun。

    输入：SQLAlchemy Session。
    输出：每次调用写入一个 succeeded PipelineRun，并记录 signal_ids。
    """

    def __init__(self, session):
        """初始化记录器。

        输入：SQLAlchemy Session。
        输出：带 calls 列表的 runner。
        """
        self.session = session
        self.calls = []

    def __call__(self, *, signal_ids, run_key, source_scope, agent_mode, allow_fallback, logger=None):
        """模拟 run_event_pipeline。

        输入：signal_ids、run_key、source_scope、agent_mode 和 allow_fallback。
        输出：带 run_id/status 的轻量对象。
        """
        self.calls.append(
            {
                "signal_ids": list(signal_ids),
                "run_key": run_key,
                "source_scope": dict(source_scope),
                "agent_mode": agent_mode,
                "allow_fallback": allow_fallback,
            }
        )
        run = PipelineRun(
            run_key=run_key,
            trigger_type="manual",
            source_scope=source_scope,
            status="succeeded",
            signals_count=len(signal_ids),
            candidates_count=1,
            dossiers_count=1,
            published_count=1,
            failed_count=0,
            summary="test pipeline succeeded",
        )
        self.session.add(run)
        self.session.flush()
        for signal_id in signal_ids:
            signal = self.session.get(SourceSignal, signal_id)
            signal.pipeline_run_id = run.id
        self.session.flush()
        return type("State", (), {"run_id": run.id, "status": "succeeded", "published_event_id": "pub_test"})()


def test_daily_pipeline_service_processes_only_signals_collected_after_run_start():
    """验证日常 pipeline 只处理本轮新增信号。

    输入：采集前旧信号、采集函数写入的新信号和 fake selector。
    输出：summary 只统计并处理新信号，旧信号保持未处理。
    """
    session = make_session()
    source = add_source(session)
    old_signal = add_signal(
        session,
        source,
        title="Old AI event",
        source_hash="old",
        collected_at=datetime(2026, 6, 24, 1, 0, tzinfo=UTC),
        original_url="https://example.com/old",
        canonical_url="https://example.com/old",
    )
    now = datetime(2026, 6, 24, 4, 0, tzinfo=UTC)

    def collect_new_signals(context):
        new_signal = add_signal(
            session,
            source,
            title="New AI event",
            source_hash="new",
            collected_at=now + timedelta(seconds=1),
            original_url="https://example.com/new",
            canonical_url="https://example.com/new",
        )
        return {"status": "succeeded", "source_keys": ["hn_algolia"], "signals_count": 2, "new_signal_id": new_signal.id}

    selector = StaticSelectorAgent()
    runner = RecordingPipelineRunner(session)
    service = DailyPipelineService(
        session,
        collector=collect_new_signals,
        selector_agent=selector,
        pipeline_runner=runner,
        now_provider=lambda: now,
    )

    summary = service.run_once(DailyPipelineConfig(max_selected=None, agent_mode="llm"))

    assert summary["raw_new_signals_count"] == 1
    assert summary["candidate_groups_count"] == 1
    assert summary["selector_selected_count"] == 1
    assert summary["pipeline_runs_count"] == 1
    assert summary["published_count"] == 1
    assert session.get(SourceSignal, old_signal.id).pipeline_run_id is None
    assert runner.calls[-1]["signal_ids"] != [old_signal.id]


def test_daily_pipeline_service_returns_no_new_signals_without_running_selector():
    """验证本轮没有新增信号时不会调用 selector 或 pipeline。

    输入：不写入任何信号的 collector。
    输出：summary.status 为 no_new_signals，selector 和 pipeline 调用次数均为 0。
    """
    session = make_session()
    selector = StaticSelectorAgent(selected_ids=[])
    runner = RecordingPipelineRunner(session)
    service = DailyPipelineService(
        session,
        collector=lambda context: {"status": "succeeded", "source_keys": [], "signals_count": 0},
        selector_agent=selector,
        pipeline_runner=runner,
        now_provider=lambda: datetime(2026, 6, 24, 4, 0, tzinfo=UTC),
    )

    summary = service.run_once(DailyPipelineConfig())

    assert summary["status"] == "no_new_signals"
    assert summary["raw_new_signals_count"] == 0
    assert selector.calls == []
    assert runner.calls == []


def test_daily_pipeline_service_applies_max_selected_limit():
    """验证 max_selected 会限制进入后续 pipeline 的数量。

    输入：3 条新信号、selector 全选、max_selected=2。
    输出：selector_selected_count 为 3，但 pipeline_runs_count 和 published_count 为 2。
    """
    session = make_session()
    source = add_source(session)
    now = datetime(2026, 6, 24, 4, 0, tzinfo=UTC)

    def collect_three_signals(context):
        titles = [
            "OpenAI unveils realtime coding workspace",
            "NVIDIA ships Blackwell inference benchmark",
            "Anthropic publishes Claude safety update",
        ]
        for index in range(3):
            add_signal(
                session,
                source,
                title=titles[index],
                source_hash=f"new-{index}",
                collected_at=now + timedelta(seconds=index + 1),
                original_url=f"https://example.com/new-{index}",
                canonical_url=f"https://example.com/new-{index}",
            )
        return {"status": "succeeded", "source_keys": ["hn_algolia"], "signals_count": 3}

    selector = StaticSelectorAgent()
    runner = RecordingPipelineRunner(session)
    service = DailyPipelineService(
        session,
        collector=collect_three_signals,
        selector_agent=selector,
        pipeline_runner=runner,
        now_provider=lambda: now,
    )
    summary = service.run_once(DailyPipelineConfig(max_selected=2, agent_mode="llm"))

    assert summary["selector_selected_count"] == 3
    assert summary["selected_groups_count"] == 2
    assert summary["pipeline_runs_count"] == 2
    assert summary["published_count"] == 2


def test_daily_pipeline_service_reports_selector_rejected_and_manual_review_counts():
    """验证 summary 保留 selector rejected 和 manual_review 数量。

    输入：3 个候选 group，selector 分别返回 selected/rejected/manual_review。
    输出：summary 中三类计数分别为 1。
    """
    session = make_session()
    source = add_source(session)
    now = datetime(2026, 6, 24, 4, 0, tzinfo=UTC)

    def collect_three_signals(context):
        titles = [
            "OpenAI unveils realtime coding workspace",
            "NVIDIA ships Blackwell inference benchmark",
            "Anthropic publishes Claude safety update",
        ]
        for index in range(3):
            add_signal(
                session,
                source,
                title=titles[index],
                source_hash=f"separate-{index}",
                collected_at=now + timedelta(seconds=index + 1),
                original_url=f"https://example.com/separate-{index}",
                canonical_url=f"https://example.com/separate-{index}",
            )
        return {"status": "succeeded", "source_keys": ["hn_algolia"], "signals_count": 3}

    selector = OrderedDecisionSelectorAgent(selected_count=1, rejected_count=1, manual_review_count=1)
    runner = RecordingPipelineRunner(session)
    service = DailyPipelineService(
        session,
        collector=collect_three_signals,
        selector_agent=selector,
        pipeline_runner=runner,
        now_provider=lambda: now,
    )
    summary = service.run_once(DailyPipelineConfig(max_selected=None, agent_mode="llm"))

    assert summary["selector_selected_count"] == 1
    assert summary["selector_rejected_count"] == 1
    assert summary["selector_manual_review_count"] == 1
    assert summary["pipeline_runs_count"] == 1
    assert summary["published_count"] == 1


def test_daily_pipeline_service_emits_key_stage_logs():
    """验证 DailyPipelineService 会输出日常流水线关键阶段日志。

    输入：一条本轮新信号、fake selector、fake pipeline runner 和内存日志 sink。
    输出：日志事件中包含运行启动、采集、新信号读取、候选构造、编辑筛选、事件生产和最终总结。
    """
    session = make_session()
    source = add_source(session)
    now = datetime(2026, 6, 24, 4, 0, tzinfo=UTC)

    def collect_one_signal(context):
        add_signal(
            session,
            source,
            title="OpenAI unveils realtime coding workspace",
            source_hash="log-new",
            collected_at=now + timedelta(seconds=1),
            original_url="https://example.com/log-new",
            canonical_url="https://example.com/log-new",
        )
        return {
            "status": "succeeded",
            "source_keys": ["hn_algolia"],
            "signals_count": 1,
            "window": {
                "lookback_hours": 8,
                "start": "2026-06-23T20:00:00+00:00",
                "end": "2026-06-24T04:00:00+00:00",
            },
            "skipped_signals": {"stale": 0, "missing_published_at": 0, "future": 0},
        }

    memory = MemorySink()
    logger = RunLogger(run_id="daily_test", sinks=[memory])
    selector = StaticSelectorAgent()
    runner = RecordingPipelineRunner(session)
    service = DailyPipelineService(
        session,
        collector=collect_one_signal,
        selector_agent=selector,
        pipeline_runner=runner,
        now_provider=lambda: now,
        logger=logger,
    )

    summary = service.run_once(DailyPipelineConfig(max_selected=None, agent_mode="llm"))

    assert summary["status"] == "succeeded"
    stage_events = {(event.stage, event.event) for event in memory.events}
    assert ("daily_pipeline", "started") in stage_events
    assert ("collect_sources", "succeeded") in stage_events
    assert ("load_new_signals", "succeeded") in stage_events
    assert ("build_candidate_groups", "succeeded") in stage_events
    assert ("editorial_selector", "succeeded") in stage_events
    assert ("candidate_pipeline", "succeeded") in stage_events
    assert ("daily_pipeline", "succeeded") in stage_events
