from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    worker_dir: Path
    runtime_dir: Path
    database_url: str
    llm_provider: str
    llm_model: str


def load_settings() -> Settings:
    root = project_root()
    load_dotenv(root / ".env")

    worker_dir = root / "apps" / "worker"
    return Settings(
        project_root=root,
        worker_dir=worker_dir,
        runtime_dir=root / "runtime",
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/ai_world_radar",
        ),
        llm_provider=os.getenv("LLM_PROVIDER", "deepseek"),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
    )
