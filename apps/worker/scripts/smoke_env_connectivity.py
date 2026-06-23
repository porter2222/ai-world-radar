from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from worker.config import load_settings, project_root
from worker.db.session import create_worker_engine
from worker.llm_client import LLMClient
from worker.models import Base


def build_arg_parser() -> argparse.ArgumentParser:
    """创建环境连通性 smoke 参数解析器。

    输入：无。
    输出：支持指定 .env、创建测试 schema 和显式真实 LLM 调用的 ArgumentParser。
    """
    parser = argparse.ArgumentParser(description="Smoke check project .env, database and optional real LLM.")
    parser.add_argument("--env-file", default=None, help="覆盖默认项目根 .env 路径。")
    parser.add_argument("--require-env-file", action="store_true", help="要求 .env 文件存在，避免误用 shell 上下文环境。")
    parser.add_argument("--create-schema-for-smoke", action="store_true", help="先创建 ORM schema，便于 fresh DB smoke。")
    parser.add_argument("--call-llm", action="store_true", help="真实调用当前 .env 配置的 LLM provider。")
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行项目环境自检。

    输入：命令行参数；默认读取项目根 `.env`。
    输出：stdout 打印脱敏 JSON 摘要；成功返回 0，数据库或 LLM 连通性失败返回 1。
    """
    args = build_arg_parser().parse_args(argv)
    env_path = _resolve_env_path(args.env_file)
    env_loaded = env_path.exists()
    if args.require_env_file and not env_loaded:
        summary = {
            "status": "failed",
            "env_file": str(env_path),
            "env_loaded": False,
            "database_connected": False,
            "llm_called": False,
            "llm_response_ok": None,
            "error_type": "FileNotFoundError",
            "error_message": "Required .env file was not found.",
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 1
    if env_loaded:
        load_dotenv(env_path, override=True)

    summary: dict[str, Any] = {
        "status": "failed",
        "env_file": str(env_path),
        "env_loaded": env_loaded,
        "database_connected": False,
        "llm_called": False,
        "llm_response_ok": None,
    }

    try:
        settings = load_settings()
        summary.update(
            {
                "llm_provider": settings.llm_provider,
                "llm_model": settings.llm_model,
                "agent_mode": settings.agent_mode,
            }
        )
        _check_database(create_schema_for_smoke=args.create_schema_for_smoke)
        summary["database_connected"] = True

        client = LLMClient()
        summary.update(
            {
                "llm_provider": client.provider,
                "llm_model": client.model,
                "llm_base_url": client.base_url,
                "api_key_present": bool(client.api_key),
            }
        )

        if args.call_llm:
            summary["llm_called"] = True
            response = client.chat("Please reply with exactly: pong")
            summary["llm_response_ok"] = "pong" in response.strip().lower()

        summary["status"] = "succeeded"
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        summary["error_type"] = exc.__class__.__name__
        summary["error_message"] = _redact_secret_fragments(str(exc))
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 1


def _resolve_env_path(raw_env_file: str | None) -> Path:
    """解析本次 smoke 使用的 .env 路径。

    输入：可选命令行 env-file 字符串。
    输出：显式路径或项目根 `.env` 的 Path。
    """
    if raw_env_file:
        return Path(raw_env_file).resolve()
    return project_root() / ".env"


def _check_database(*, create_schema_for_smoke: bool) -> None:
    """检查当前 `.env` 中 DATABASE_URL 是否可连接。

    输入：是否先按 ORM metadata 创建 schema。
    输出：连接成功时无返回；失败时抛出 SQLAlchemy 异常。
    """
    engine = create_worker_engine()
    if create_schema_for_smoke:
        Base.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(text("select 1")).scalar_one()


def _redact_secret_fragments(message: str) -> str:
    """对错误消息做基础脱敏。

    输入：异常文本。
    输出：去掉常见 URL 密码片段后的文本，避免 stdout 泄露 `.env` 中的敏感值。
    """
    sanitized = message
    if "://" in sanitized and "@" in sanitized:
        prefix, suffix = sanitized.split("://", maxsplit=1)
        credentials, rest = suffix.split("@", maxsplit=1)
        if ":" in credentials:
            user = credentials.split(":", maxsplit=1)[0]
            sanitized = f"{prefix}://{user}:***@{rest}"
    return sanitized


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
