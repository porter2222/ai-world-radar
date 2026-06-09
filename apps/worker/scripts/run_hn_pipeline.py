from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from worker.config import load_settings
from worker.db.session import create_session_factory
from worker.pipelines.hn_event_pipeline import HNEventPipeline


def build_arg_parser() -> argparse.ArgumentParser:
    """构建本地运行参数解析器。

    输入：无。
    输出：支持 `--days`、`--limit`、`--force` 的 argparse parser。
    """
    parser = argparse.ArgumentParser(description="Run the backend P1 Hacker News event pipeline.")
    parser.add_argument("--days", type=int, default=7, help="HN search window in days.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum HN stories to keep after dedupe and ranking.")
    parser.add_argument("--force", action="store_true", help="Regenerate existing evidence/content where supported.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行 HN pipeline 本地入口。

    输入：命令行参数列表；为空时由 `__main__` 传入真实 argv。
    输出：进程退出码；成功返回 0，pipeline 失败返回 1。
    """
    args = build_arg_parser().parse_args(argv)
    settings = load_settings()
    session_factory = create_session_factory(settings.database_url)

    with session_factory() as session:
        pipeline = HNEventPipeline(session=session, runtime_dir=settings.runtime_dir)
        result = pipeline.run(days=args.days, limit=args.limit, force=args.force)

    print(f"Pipeline run: {result.pipeline_run_id}")
    print(f"Status: {result.status}")
    print(f"Fetched stories: {result.fetched_count}")
    print(f"Evidence cards: {result.evidence_card_count}")
    print(f"Event clusters: {result.event_cluster_count}")
    print(f"Published events: {result.published_event_count}")
    print(f"Brief items: {result.brief_item_count}")
    if result.report_path:
        print(f"Report: {result.report_path}")
    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"- {error}")
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
