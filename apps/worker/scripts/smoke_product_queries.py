from __future__ import annotations

import argparse
import json

from sqlalchemy.orm import sessionmaker

from worker.db.session import create_worker_engine
from worker.services.product_query_service import ProductQueryService


def parse_args() -> argparse.Namespace:
    """解析产品查询 smoke 脚本参数。

    输入：命令行参数，可选 `--database-url` 覆盖默认配置。
    输出：包含 database_url 的 argparse Namespace。
    """
    parser = argparse.ArgumentParser(description="Read product API data from an existing database.")
    parser.add_argument("--database-url", default=None, help="覆盖默认 DATABASE_URL；输出中不会回显该值。")
    return parser.parse_args()


def main() -> int:
    """执行产品查询只读 smoke。

    输入：命令行参数和已有数据库。
    输出：stdout 打印 JSON 摘要；成功返回 0，异常返回 1。
    """
    args = parse_args()
    engine = create_worker_engine(args.database_url) if args.database_url else create_worker_engine()
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        summary = build_smoke_summary(ProductQueryService(session))
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        session.rollback()
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    finally:
        session.close()
        engine.dispose()


def build_smoke_summary(service: ProductQueryService) -> dict[str, object]:
    """读取产品接口层核心查询并生成摘要。

    输入：ProductQueryService，只允许执行只读查询。
    输出：不包含数据库连接串的 smoke 结果摘要。
    """
    events = service.list_published_events(limit=20)
    first_event = events[0] if events else None
    event_detail = service.get_event_by_slug(first_event.slug) if first_event else None

    pipeline_runs = service.list_pipeline_runs(limit=20)
    first_run = pipeline_runs[0] if pipeline_runs else None
    agent_runs = service.list_agent_runs(first_run.id) if first_run else []

    review_queue = service.list_manual_review_items(limit=20)

    return {
        "status": "succeeded",
        "events_count": len(events),
        "detail_found": event_detail is not None,
        "first_event_slug": first_event.slug if first_event else None,
        "pipeline_runs_count": len(pipeline_runs),
        "first_pipeline_run_id": first_run.id if first_run else None,
        "agent_runs_count": len(agent_runs),
        "review_queue_count": len(review_queue),
    }


if __name__ == "__main__":
    raise SystemExit(main())
