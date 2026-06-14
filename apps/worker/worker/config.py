from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def project_root() -> Path:
    """返回项目根目录。

    输入：无。
    输出：项目根目录这一层的 Path，用于定位 `.env`、`runtime` 和应用目录。
    """
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    """Worker 运行配置。

    输入：由 `load_settings` 从环境变量和默认值组装。
    输出：供数据库连接、runtime 目录、LLM 配置和 Agent 模式读取的不可变配置对象。
    """

    project_root: Path
    worker_dir: Path
    runtime_dir: Path
    database_url: str
    llm_provider: str
    llm_model: str
    agent_mode: str


def load_settings() -> Settings:
    """读取 Worker 配置。

    输入：项目根目录下的 `.env` 和当前系统环境变量。
    输出：`Settings`，包含数据库 URL、runtime 路径、默认 LLM provider/model 和 Agent 模式。
    """
    root = project_root()
    load_dotenv(root / ".env")

    worker_dir = root / "apps" / "worker"
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    llm_model = os.getenv("LLM_MODEL", _default_llm_model(llm_provider))
    return Settings(
        project_root=root,
        worker_dir=worker_dir,
        runtime_dir=root / "runtime",
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/ai_world_radar",
        ),
        llm_provider=llm_provider,
        llm_model=llm_model,
        agent_mode=os.getenv("AGENT_MODE", "stub"),
    )


def _default_llm_model(provider: str) -> str:
    """按 provider 返回默认模型名。

    输入：LLM provider 名称，例如 openai、deepseek 或 qwen-cn。
    输出：该 provider 在未显式配置 LLM_MODEL 时使用的模型名。
    """
    if provider == "deepseek":
        return "deepseek-chat"
    if provider == "qwen-cn":
        return "qwen-plus"
    return "gpt-4o-mini"
