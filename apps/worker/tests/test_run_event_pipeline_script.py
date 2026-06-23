import json
import sqlite3
import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from scripts.run_event_pipeline import parse_args


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
