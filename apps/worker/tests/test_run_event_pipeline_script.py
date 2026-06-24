import json
import sqlite3
import subprocess
import sys
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base, PipelineRun
from worker.schemas.editorial_selection import EditorialSelectedItem, EditorialSelectionResult
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.schemas.workflow import EventPipelineState
from worker.services.editorial_candidate_service import EditorialCandidateGroup
from worker.services.signal_service import SignalService
from scripts.run_event_pipeline import parse_args, resolve_candidate_concurrency, run_selector_pipeline, select_candidate_groups


def seed_hn_signal(db_path):
    """向临时 SQLite 写入一条 HN SourceSignal。

    输入：SQLite 文件路径。
    输出：已提交到数据库的 SourceSignal ID。
    """
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        service = SignalService(session)
        service.upsert_source(
            SourceCreate(
                source_key="hn_algolia",
                name="Hacker News Algolia",
                source_type="community",
                fetch_method="api",
                entry_url="https://hn.algolia.com/api/v1/search_by_date",
            )
        )
        signal = service.upsert_signal(
            SourceSignalCreate(
                source_key="hn_algolia",
                source_item_id="1001",
                original_title="OpenAI launches a new coding agent",
                original_url="https://example.com/openai-coding-agent",
                raw_summary="HN discussion about a new coding agent.",
                source_hash="hn_algolia:1001",
                heat_metrics={"points": 41, "comments": 12, "hn_heat_score": 65},
            )
        )
        session.commit()
        return signal.id
    finally:
        session.close()
        engine.dispose()


def seed_two_selector_signals(db_path):
    """向临时 SQLite 写入两个可被 selector 分成不同 group 的 SourceSignal。

    输入：SQLite 文件路径。
    输出：已提交到数据库的 SourceSignal ID 列表。
    """
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        service = SignalService(session)
        service.upsert_source(
            SourceCreate(
                source_key="hn_algolia",
                name="Hacker News Algolia",
                source_type="community",
                fetch_method="api",
                entry_url="https://hn.algolia.com/api/v1/search_by_date",
            )
        )
        hot_signal = service.upsert_signal(
            SourceSignalCreate(
                source_key="hn_algolia",
                source_item_id="2001",
                original_title="OpenAI launches a new coding agent",
                original_url="https://example.com/openai-coding-agent",
                canonical_url="https://example.com/openai-coding-agent",
                raw_summary="HN discussion about a new coding agent.",
                source_hash="hn_algolia:2001",
                heat_metrics={"points": 88, "comments": 24},
            )
        )
        minor_signal = service.upsert_signal(
            SourceSignalCreate(
                source_key="hn_algolia",
                source_item_id="2002",
                original_title="Small dependency patch release",
                original_url="https://example.com/dependency-patch",
                canonical_url="https://example.com/dependency-patch",
                raw_summary="A small dependency patch release.",
                source_hash="hn_algolia:2002",
                heat_metrics={"points": 2, "comments": 0},
            )
        )
        session.commit()
        return [hot_signal.id, minor_signal.id]
    finally:
        session.close()
        engine.dispose()


def seed_three_selector_signals(db_path):
    """向临时 SQLite 写入三个可被 selector 分成不同 group 的 SourceSignal。
    输入：SQLite 文件路径。
    输出：已提交到数据库的 SourceSignal ID 列表。
    """
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        service = SignalService(session)
        service.upsert_source(
            SourceCreate(
                source_key="hn_algolia",
                name="Hacker News Algolia",
                source_type="community",
                fetch_method="api",
                entry_url="https://hn.algolia.com/api/v1/search_by_date",
            )
        )
        signal_ids = []
        events = [
            ("3000", "OpenAI launches browser automation agent", "https://example.com/openai-browser-agent"),
            ("3001", "NVIDIA releases robotics foundation model", "https://example.com/nvidia-robotics-model"),
            ("3002", "Anthropic updates Claude enterprise workspace", "https://example.com/anthropic-workspace"),
        ]
        for index, (source_item_id, title, url) in enumerate(events):
            signal = service.upsert_signal(
                SourceSignalCreate(
                    source_key="hn_algolia",
                    source_item_id=source_item_id,
                    original_title=title,
                    original_url=url,
                    canonical_url=url,
                    raw_summary=f"Signal {index} for candidate-level parallel pipeline testing.",
                    source_hash=f"hn_algolia:{source_item_id}",
                    heat_metrics={"points": 80 - index, "comments": 20 - index},
                )
            )
            signal_ids.append(signal.id)
        session.commit()
        return signal_ids
    finally:
        session.close()
        engine.dispose()


def query_pipeline_counts(db_path):
    """查询 pipeline 脚本测试数据库核心计数。

    输入：SQLite 文件路径。
    输出：pipeline_runs、event_candidates、published_events 的行数字典。
    """
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        return {
            "pipeline_runs": cursor.execute("select count(*) from pipeline_runs").fetchone()[0],
            "event_candidates": cursor.execute("select count(*) from event_candidates").fetchone()[0],
            "published_events": cursor.execute("select count(*) from published_events").fetchone()[0],
        }
    finally:
        connection.close()


def query_pipeline_run_keys(db_path):
    """读取测试数据库里的 pipeline run key。
    输入：SQLite 文件路径。
    输出：按 run_key 排序的 run key 列表。
    """
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        rows = cursor.execute("select run_key from pipeline_runs order by run_key").fetchall()
        return [row[0] for row in rows]
    finally:
        connection.close()


class BrokenSessionSelectorAgent:
    """模拟 selector LLM 初始化或调用失败的测试 Agent。

    输入：无。
    输出：select 时抛出 RuntimeError。
    """

    def select(self, candidate_groups):
        """始终抛出 selector 失败。

        输入：candidate group dict 列表。
        输出：抛出 RuntimeError。
        """
        raise RuntimeError("fake selector provider failure")


class RecordingBatchSelectorAgent:
    """记录 selector 分批调用情况的测试 Agent。
    输入：每次 select 收到的 candidate group dict 列表。
    输出：把每个输入 group 都作为 selected 返回，便于验证分批不会漏选。
    """

    def __init__(self):
        """初始化记录容器。
        输入：无。
        输出：带 batches 记录列表的测试 Agent。
        """
        self.batches = []

    def select(self, candidate_groups):
        """记录本批输入并把本批所有 group 标为 selected。
        输入：本批 candidate group dict 列表。
        输出：EditorialSelectionResult，selected 数量等于本批输入数量。
        """
        self.batches.append(candidate_groups)
        return EditorialSelectionResult(
            selected=[
                EditorialSelectedItem(
                    candidate_group_id=group["candidate_group_id"],
                    signal_ids=group["signal_ids"],
                    event_title=group["title"],
                    priority_score=90,
                    suggested_angle="测试分批 selector 合并。",
                    reason="fake selector selected this group.",
                )
                for group in candidate_groups
            ],
            rejected=[],
            manual_review=[],
        )


class RecordingWorkflow:
    """记录并发 candidate 处理情况的 fake workflow。
    输入：run_selector_pipeline 传入的 session、signal_ids 和 run_key。
    输出：在当前 session 写入最小 PipelineRun，并返回 EventPipelineState。
    """

    def __init__(self, *, fail_on_run_key: str | None = None, sleep_seconds: float = 0.05):
        """初始化记录容器。
        输入：可选失败 run_key 和模拟耗时。
        输出：可调用的 fake workflow。
        """
        self.fail_on_run_key = fail_on_run_key
        self.sleep_seconds = sleep_seconds
        self.calls = []
        self.lock = threading.Lock()

    def __call__(
        self,
        session,
        *,
        signal_ids,
        run_key,
        source_scope=None,
        agent_mode="llm",
        allow_fallback=True,
    ):
        """模拟单条 candidate pipeline 执行。
        输入：独立 session、信号 ID、run_key、source_scope 和 Agent 配置。
        输出：EventPipelineState；指定 run_key 时抛出 RuntimeError。
        """
        with self.lock:
            self.calls.append(
                {
                    "run_key": run_key,
                    "signal_ids": list(signal_ids),
                    "session_id": id(session),
                    "thread_id": threading.get_ident(),
                    "source_scope": dict(source_scope or {}),
                    "agent_mode": agent_mode,
                    "allow_fallback": allow_fallback,
                }
            )
        time.sleep(self.sleep_seconds)
        if self.fail_on_run_key == run_key:
            raise RuntimeError(f"fake workflow failed for {run_key}")

        run = PipelineRun(
            run_key=run_key,
            source_scope=dict(source_scope or {}),
            status="succeeded",
            signals_count=len(signal_ids),
            candidates_count=1,
            dossiers_count=1,
            published_count=1,
            failed_count=0,
            summary="fake workflow succeeded",
        )
        session.add(run)
        session.flush()
        return EventPipelineState(
            run_id=run.id,
            run_key=run_key,
            signal_ids=list(signal_ids),
            source_scope=dict(source_scope or {}),
            status="succeeded",
            published_event_id=f"pub_{run_key}",
        )


def test_run_event_pipeline_script_smoke(tmp_path):
    """验证新版脚本入口可以用 demo signal 跑通首跑发布。

    输入：临时 SQLite 数据库、--create-schema-for-smoke、--seed-demo-signal。
    输出：脚本返回 0，并在 stdout 输出 published_count=1。
    """
    db_path = tmp_path / "p1_2_script_smoke.sqlite"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_event_pipeline.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--create-schema-for-smoke",
            "--seed-demo-signal",
            "--agent-mode",
            "stub",
            "--run-key",
            "manual-p1-2-script",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "succeeded"
    assert summary["published_count"] == 1


def test_run_event_pipeline_script_consumes_collected_source_signals(tmp_path):
    """验证新版脚本可以从已入库 source_signals 选择信号运行。

    输入：预置 hn_algolia SourceSignal 的临时 SQLite 数据库、--source-key、--limit。
    输出：脚本返回 0，stdout 显示 published_count=1 且 signals_count=1。
    """
    db_path = tmp_path / "p1_3_script_collected_signal.sqlite"
    seed_hn_signal(db_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_event_pipeline.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--source-key",
            "hn_algolia",
            "--limit",
            "1",
            "--agent-mode",
            "stub",
            "--run-key",
            "manual-p1-3-collected-source",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "succeeded"
    assert summary["signals_count"] == 1
    assert summary["published_count"] == 1


def test_run_event_pipeline_script_accepts_agent_mode_argument(monkeypatch):
    """验证脚本接受 --agent-mode stub|llm。

    输入：包含 --agent-mode llm 的命令行参数。
    输出：parse_args 返回 agent_mode=llm。
    """
    monkeypatch.setattr(sys, "argv", ["run_event_pipeline.py", "--agent-mode", "llm"])

    args = parse_args()

    assert args.agent_mode == "llm"


def test_run_event_pipeline_script_accepts_disable_agent_fallback_argument(monkeypatch):
    """验证脚本支持禁用 Agent fallback 的严格验收参数。

    输入：包含 --disable-agent-fallback 的命令行参数。
    输出：parse_args 返回 disable_agent_fallback=True。
    """
    monkeypatch.setattr(sys, "argv", ["run_event_pipeline.py", "--disable-agent-fallback"])

    args = parse_args()

    assert args.disable_agent_fallback is True


def test_run_event_pipeline_script_defaults_candidate_concurrency_to_three(monkeypatch):
    """验证 selector pipeline 默认使用候选级并发 3。
    输入：不包含 --candidate-concurrency 的命令行参数。
    输出：parse_args 返回 candidate_concurrency=3。
    """
    monkeypatch.setattr(sys, "argv", ["run_event_pipeline.py", "--select-all-candidates"])

    args = parse_args()

    assert args.candidate_concurrency == 3


def test_resolve_candidate_concurrency_rejects_values_outside_safe_range():
    """验证候选级并发只允许 1 到 5。
    输入：0、6 和合法值 3。
    输出：非法值抛出 ValueError，合法值原样返回。
    """
    with pytest.raises(ValueError, match="between 1 and 5"):
        resolve_candidate_concurrency(0)
    with pytest.raises(ValueError, match="between 1 and 5"):
        resolve_candidate_concurrency(6)

    assert resolve_candidate_concurrency(3) == 3


def test_run_selector_pipeline_falls_back_to_stub_when_llm_selector_fails(tmp_path):
    """验证默认 LLM selector 异常时会降级到 stub selector。

    输入：两个 selector group、agent_mode=llm、会失败的 selector agent 和 fake workflow。
    输出：stdout summary 标记 selector fallback，且只运行 fallback selected Top 1，不触发真实 writer/reviewer LLM。
    """
    db_path = tmp_path / "p1_9_selector_fallback.sqlite"
    seed_two_selector_signals(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    workflow = RecordingWorkflow()
    try:
        args = type(
            "Args",
            (),
            {
                "select_top_candidates": 1,
                "select_all_candidates": False,
                "candidate_pool_limit": 60,
                "candidate_concurrency": 1,
                "selector_batch_size": None,
                "run_key": "manual-p1-9-selector-fallback",
            },
        )()

        summary = run_selector_pipeline(
            session,
            args=args,
            agent_mode="llm",
            selector_agent=BrokenSessionSelectorAgent(),
            workflow_runner=workflow,
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    counts = query_pipeline_counts(db_path)

    assert summary["status"] == "succeeded"
    assert summary["selector_mode"] == "stub_fallback"
    assert summary["selector_fallback_reason"] == "fake selector provider failure"
    assert summary["selected_groups_count"] == 1
    assert summary["published_count"] == 1
    assert len(workflow.calls) == 1
    assert counts["pipeline_runs"] == 1
    assert counts["event_candidates"] == 0
    assert counts["published_events"] == 0


def test_run_selector_pipeline_raises_when_selector_fallback_is_disabled(tmp_path):
    """验证严格真实 selector 模式不会用 stub 兜底冒充成功。

    输入：两个 selector group、agent_mode=llm、会失败的 selector agent、allow_fallback=False。
    输出：抛出原始 selector 异常，且不创建 pipeline run、event candidate 或 published event。
    """
    db_path = tmp_path / "p1_9_selector_strict_failure.sqlite"
    seed_two_selector_signals(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        args = type(
            "Args",
            (),
            {
                "select_top_candidates": 1,
                "select_all_candidates": False,
                "candidate_pool_limit": 60,
                "candidate_concurrency": 1,
                "selector_batch_size": None,
                "run_key": "manual-p1-9-selector-strict-failure",
            },
        )()

        with pytest.raises(RuntimeError, match="fake selector provider failure"):
            run_selector_pipeline(
                session,
                args=args,
                agent_mode="llm",
                selector_agent=BrokenSessionSelectorAgent(),
                allow_fallback=False,
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()

    counts = query_pipeline_counts(db_path)

    assert counts == {"pipeline_runs": 0, "event_candidates": 0, "published_events": 0}


def test_select_candidate_groups_batches_llm_selector_without_dropping_selected_items():
    """验证 LLM selector 可以分批处理候选全集并合并结果。
    输入：3 个候选 group、batch_size=1 和会全选的 fake selector。
    输出：selector 被调用 3 次，最终 selected 合并为 3 条，没有因为分批被截断。
    """
    groups = [
        EditorialCandidateGroup(
            group_id=f"group_{index}",
            group_key=f"url:https://example.com/{index}",
            title=f"AI event {index}",
            signal_ids=[f"sig_{index}"],
            source_keys=["hn_algolia"],
            canonical_url=f"https://example.com/{index}",
        )
        for index in range(3)
    ]
    selector_agent = RecordingBatchSelectorAgent()

    outcome = select_candidate_groups(
        groups,
        top_n=3,
        agent_mode="llm",
        selector_agent=selector_agent,
        allow_fallback=False,
        batch_size=1,
    )

    assert [len(batch) for batch in selector_agent.batches] == [1, 1, 1]
    assert outcome.selector_mode == "llm"
    assert [item.candidate_group_id for item in outcome.selection.selected] == ["group_0", "group_1", "group_2"]


def test_run_event_pipeline_script_consumes_selector_selected_top_candidates(tmp_path):
    """验证脚本只对 selector 选中的 Top N group 运行发布流程。

    输入：两个不同 candidate group 的 source_signals、`--select-top-candidates 1`。
    输出：只创建 1 个 pipeline run 和 1 条 published_event，rejected group 不发布。
    """
    db_path = tmp_path / "p1_9_selector_pipeline.sqlite"
    seed_two_selector_signals(db_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_event_pipeline.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--select-top-candidates",
            "1",
            "--agent-mode",
            "stub",
            "--run-key",
            "manual-p1-9-selector-script",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)
    counts = query_pipeline_counts(db_path)

    assert summary["status"] == "succeeded"
    assert summary["selector_mode"] == "stub"
    assert summary["selected_groups_count"] == 1
    assert summary["rejected_groups_count"] == 1
    assert summary["pipeline_runs_count"] == 1
    assert summary["published_count"] == 1
    assert counts == {"pipeline_runs": 1, "event_candidates": 1, "published_events": 1}


def test_run_selector_pipeline_parallel_candidates_use_independent_sessions(tmp_path):
    """验证 selector 选中的多条候选可并发运行且每条使用独立 session。
    输入：3 个 selected groups、candidate_concurrency=3 和 fake workflow。
    输出：3 个 pipeline run 均提交；fake workflow 记录到 3 个不同 session，且不是主 session。
    """
    db_path = tmp_path / "p1_11_parallel_candidates.sqlite"
    seed_three_selector_signals(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionFactory()
    workflow = RecordingWorkflow()
    try:
        args = type(
            "Args",
            (),
            {
                "select_top_candidates": None,
                "select_all_candidates": True,
                "candidate_pool_limit": 60,
                "candidate_concurrency": 3,
                "selector_batch_size": None,
                "run_key": "manual-p1-11-parallel",
            },
        )()

        summary = run_selector_pipeline(
            session,
            args=args,
            agent_mode="stub",
            session_factory=SessionFactory,
            workflow_runner=workflow,
        )
    finally:
        session.close()
        engine.dispose()

    counts = query_pipeline_counts(db_path)
    session_ids = {call["session_id"] for call in workflow.calls}
    thread_ids = {call["thread_id"] for call in workflow.calls}

    assert summary["status"] == "succeeded"
    assert summary["candidate_concurrency"] == 3
    assert summary["pipeline_runs_count"] == 3
    assert summary["published_count"] == 3
    assert summary["failed_count"] == 0
    assert counts["pipeline_runs"] == 3
    assert len(workflow.calls) == 3
    assert len(session_ids) == 3
    assert id(session) not in session_ids
    assert len(thread_ids) > 1


def test_run_selector_pipeline_parallel_candidate_failure_does_not_block_successes(tmp_path):
    """验证并发候选中单条失败不会阻塞其他候选提交。
    输入：3 个 selected groups、candidate_concurrency=3，其中第 2 条 fake workflow 失败。
    输出：summary 为 partial_failed，成功的 2 条提交，失败条目进入 candidate_results。
    """
    db_path = tmp_path / "p1_11_parallel_partial_failure.sqlite"
    seed_three_selector_signals(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionFactory()
    workflow = RecordingWorkflow(fail_on_run_key="manual-p1-11-partial-2")
    try:
        args = type(
            "Args",
            (),
            {
                "select_top_candidates": None,
                "select_all_candidates": True,
                "candidate_pool_limit": 60,
                "candidate_concurrency": 3,
                "selector_batch_size": None,
                "run_key": "manual-p1-11-partial",
            },
        )()

        summary = run_selector_pipeline(
            session,
            args=args,
            agent_mode="stub",
            session_factory=SessionFactory,
            workflow_runner=workflow,
        )
    finally:
        session.close()
        engine.dispose()

    counts = query_pipeline_counts(db_path)
    run_keys = query_pipeline_run_keys(db_path)
    failed_results = [item for item in summary["candidate_results"] if item["status"] == "failed"]

    assert summary["status"] == "partial_failed"
    assert summary["pipeline_runs_count"] == 2
    assert summary["published_count"] == 2
    assert summary["failed_count"] == 1
    assert counts["pipeline_runs"] == 2
    assert run_keys == ["manual-p1-11-partial-1", "manual-p1-11-partial-3"]
    assert len(failed_results) == 1
    assert failed_results[0]["candidate_group_id"]
    assert failed_results[0]["run_key"] == "manual-p1-11-partial-2"
    assert failed_results[0]["status"] == "failed"
    assert failed_results[0]["error"] == "fake workflow failed for manual-p1-11-partial-2"


def test_run_selector_pipeline_candidate_concurrency_one_still_isolates_transactions(tmp_path):
    """验证并发数为 1 时也不会用主事务串行吞掉已成功候选。
    输入：3 个 selected groups、candidate_concurrency=1，其中第 2 条 fake workflow 失败。
    输出：第 1、3 条仍分别提交，失败只影响自己的独立 session。
    """
    db_path = tmp_path / "p1_11_concurrency_one_isolation.sqlite"
    seed_three_selector_signals(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionFactory()
    workflow = RecordingWorkflow(fail_on_run_key="manual-p1-11-concurrency-one-2")
    try:
        args = type(
            "Args",
            (),
            {
                "select_top_candidates": None,
                "select_all_candidates": True,
                "candidate_pool_limit": 60,
                "candidate_concurrency": 1,
                "selector_batch_size": None,
                "run_key": "manual-p1-11-concurrency-one",
            },
        )()

        summary = run_selector_pipeline(
            session,
            args=args,
            agent_mode="stub",
            session_factory=SessionFactory,
            workflow_runner=workflow,
        )
    finally:
        session.close()
        engine.dispose()

    counts = query_pipeline_counts(db_path)
    run_keys = query_pipeline_run_keys(db_path)
    session_ids = {call["session_id"] for call in workflow.calls}

    assert summary["status"] == "partial_failed"
    assert summary["candidate_concurrency"] == 1
    assert summary["pipeline_runs_count"] == 2
    assert summary["published_count"] == 2
    assert summary["failed_count"] == 1
    assert counts["pipeline_runs"] == 2
    assert run_keys == ["manual-p1-11-concurrency-one-1", "manual-p1-11-concurrency-one-3"]
    assert id(session) not in session_ids
