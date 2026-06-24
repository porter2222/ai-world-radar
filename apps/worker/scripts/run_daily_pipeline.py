from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from worker.config import load_settings
from worker.db.session import create_worker_engine
from worker.services.daily_pipeline_service import DailyPipelineConfig, DailyPipelineService


def build_arg_parser() -> argparse.ArgumentParser:
    """创建手动日常 pipeline CLI 参数解析器。

    输入：无。
    输出：支持可选 `--env-file` 的 ArgumentParser；正常手动运行不需要传参。
    """
    parser = argparse.ArgumentParser(description="Run AI World Radar manual daily pipeline once.")
    parser.add_argument("--env-file", default=None, help="测试或本地诊断时覆盖项目根 .env 路径。")
    return parser


def main(argv: list[str] | None = None) -> int:
    """运行一次手动日常全流程。

    输入：可选命令行参数；默认读取项目根 `.env`。
    输出：stdout 打印脱敏 JSON summary；返回码 0 表示可接受完成，1 表示失败，2 表示部分失败。
    """
    args = build_arg_parser().parse_args(argv)
    if args.env_file:
        load_dotenv(Path(args.env_file).resolve(), override=True)

    settings = load_settings()
    config = DailyPipelineConfig.from_env(settings)
    engine = create_worker_engine()
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        service = DailyPipelineService(session)
        summary = service.run_once(config)
        session.commit()
        print(json.dumps(_public_summary(summary), ensure_ascii=False, sort_keys=True))
        return _exit_code_for_status(str(summary.get("status", "failed")))
    except Exception as exc:
        session.rollback()
        summary = {
            "status": "failed",
            "error_type": exc.__class__.__name__,
            "error_message": _redact_secret_fragments(str(exc)),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 1
    finally:
        session.close()
        engine.dispose()


def _public_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """生成可打印到 stdout 的公开 summary。

    输入：DailyPipelineService 返回的 summary。
    输出：移除可能误带入的数据库连接、API key 等敏感字段后的 summary。
    """
    blocked_keys = {"database_url", "api_key", "openai_api_key", "secret", "password"}
    return {key: value for key, value in summary.items() if key.lower() not in blocked_keys}


def _exit_code_for_status(status: str) -> int:
    """把业务状态转换为进程退出码。

    输入：DailyPipelineService summary.status。
    输出：0 表示成功或无可处理数据，2 表示部分失败，1 表示失败。
    """
    if status in {"succeeded", "no_new_signals", "no_candidate_groups", "no_selected_candidates"}:
        return 0
    if status == "partial_failed":
        return 2
    return 1


def _redact_secret_fragments(message: str) -> str:
    """对异常消息做基础脱敏。

    输入：异常文本。
    输出：隐藏 URL 密码片段和常见 key 字样后的文本，避免 stdout 泄露本地 `.env`。
    """
    sanitized = message
    if "://" in sanitized and "@" in sanitized:
        prefix, suffix = sanitized.split("://", maxsplit=1)
        credentials, rest = suffix.split("@", maxsplit=1)
        if ":" in credentials:
            user = credentials.split(":", maxsplit=1)[0]
            sanitized = f"{prefix}://{user}:***@{rest}"
    return sanitized.replace("OPENAI_API_KEY", "OPENAI_API_KEY_REDACTED")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
