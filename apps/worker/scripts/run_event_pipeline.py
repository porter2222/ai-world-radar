from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.db.session import create_worker_engine
from worker.models import Base, PipelineRun
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.workflows.event_pipeline import run_event_pipeline


def parse_args() -> argparse.Namespace:
    """解析新版事件 pipeline 脚本参数。

    输入：命令行参数。
    输出：包含数据库 URL、run_key 和 smoke 开关的 argparse Namespace。
    """
    parser = argparse.ArgumentParser(description="Run the P1-2 event dossier pipeline.")
    parser.add_argument("--database-url", default=None, help="覆盖默认 DATABASE_URL。")
    parser.add_argument("--run-key", default=None, help="本轮 pipeline run key。")
    parser.add_argument("--create-schema-for-smoke", action="store_true", help="仅本地 smoke 使用：直接 create_all。")
    parser.add_argument("--seed-demo-signal", action="store_true", help="写入一条 demo SourceSignal 后运行。")
    return parser.parse_args()


def main() -> int:
    """运行新版事件 pipeline 脚本。

    输入：命令行参数和可选临时数据库。
    输出：向 stdout 打印 JSON 摘要，并用进程退出码表达成功或失败。
    """
    args = parse_args()
    engine = create_worker_engine(args.database_url) if args.database_url else create_worker_engine()
    if args.create_schema_for_smoke:
        Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        signal_ids = seed_demo_signal(session) if args.seed_demo_signal else []
        if not signal_ids:
            raise ValueError("No signal_ids available. Use --seed-demo-signal for local smoke.")
        run_key = args.run_key or f"manual-p1-2-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        state = run_event_pipeline(
            session,
            signal_ids=signal_ids,
            run_key=run_key,
            source_scope={"source": "demo" if args.seed_demo_signal else "manual"},
        )
        session.commit()

        run = session.scalar(select(PipelineRun).where(PipelineRun.id == state.run_id))
        summary = {
            "status": state.status,
            "run_id": state.run_id,
            "published_event_id": state.published_event_id,
            "signals_count": run.signals_count if run else 0,
            "candidates_count": run.candidates_count if run else 0,
            "dossiers_count": run.dossiers_count if run else 0,
            "published_count": run.published_count if run else 0,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        session.rollback()
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    finally:
        session.close()
        engine.dispose()


def seed_demo_signal(session) -> list[str]:
    """写入 demo 来源和来源信号。

    输入：调用方管理事务的 SQLAlchemy Session。
    输出：可传给 workflow 的 SourceSignal ID 列表。
    """
    service = SignalService(session)
    service.upsert_source(
        SourceCreate(
            source_key="demo",
            name="Demo Source",
            source_type="fixture",
            fetch_method="manual",
            entry_url="https://example.com/demo",
        )
    )
    signal = service.upsert_signal(
        SourceSignalCreate(
            source_key="demo",
            source_item_id="demo-1",
            original_title="OpenAI releases a new developer tool",
            original_url="https://example.com/openai-tool",
            raw_summary="Developers discuss the new tool and pricing.",
            source_hash="demo:openai-developer-tool",
            heat_metrics={"points": 120, "comments": 45},
        )
    )
    return [signal.id]


if __name__ == "__main__":
    raise SystemExit(main())
