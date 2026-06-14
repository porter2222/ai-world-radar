import json
import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService


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
