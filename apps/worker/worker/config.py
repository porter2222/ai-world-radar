from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


def project_root() -> Path:
    """返回项目根目录。

    输入：无。
    输出：项目根目录这一层的 Path，用于定位 `.env`、`runtime` 和应用目录。
    """
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class RuntimeSettings:
    """运行环境配置。"""

    project_root: Path
    worker_dir: Path
    runtime_dir: Path
    database_url: str


@dataclass(frozen=True)
class LLMSettings:
    """LLM 调用配置。"""

    provider: str
    model: str
    request_timeout_seconds: int


@dataclass(frozen=True)
class ProductSettings:
    """产品展示策略配置。"""

    homepage_recent_hours: int
    homepage_default_limit: int
    homepage_max_limit: int
    homepage_min_recent_items: int
    homepage_backfill_days: int | None


@dataclass(frozen=True)
class DailyPipelineSettings:
    """日常流水线运行策略配置。"""

    source_group: str
    lookback_hours: int
    candidate_lookback_hours: int
    selector_batch_size: int
    max_selected: int | None
    continue_on_source_error: bool
    disable_agent_fallback: bool


@dataclass(frozen=True)
class SchedulerSettings:
    """本地调度策略配置。"""

    timezone: str
    daily_pipeline_times: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    """Worker 运行配置入口。

    输入：由 `load_settings` 从环境变量和默认值组装。
    输出：供数据库、LLM、产品查询、日常流水线和调度读取的不可变配置对象。
    """

    runtime: RuntimeSettings
    llm: LLMSettings
    product: ProductSettings
    daily_pipeline: DailyPipelineSettings
    scheduler: SchedulerSettings
    agent_mode: str

    @property
    def project_root(self) -> Path:
        """兼容旧调用方读取项目根目录。"""
        return self.runtime.project_root

    @property
    def worker_dir(self) -> Path:
        """兼容旧调用方读取 worker 目录。"""
        return self.runtime.worker_dir

    @property
    def runtime_dir(self) -> Path:
        """兼容旧调用方读取 runtime 目录。"""
        return self.runtime.runtime_dir

    @property
    def database_url(self) -> str:
        """兼容旧调用方读取数据库 URL。"""
        return self.runtime.database_url

    @property
    def llm_provider(self) -> str:
        """兼容旧调用方读取 LLM provider。"""
        return self.llm.provider

    @property
    def llm_model(self) -> str:
        """兼容旧调用方读取 LLM model。"""
        return self.llm.model


def load_settings() -> Settings:
    """读取 Worker 配置。

    输入：项目根目录下的 `.env` 和当前系统环境变量。
    输出：分层 `Settings`，并保留旧属性兼容。
    """
    root = project_root()
    load_dotenv(root / ".env")

    worker_dir = root / "apps" / "worker"
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    llm_model = os.getenv("LLM_MODEL", _default_llm_model(llm_provider))

    runtime = RuntimeSettings(
        project_root=root,
        worker_dir=worker_dir,
        runtime_dir=root / "runtime",
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/ai_world_radar",
        ),
    )
    llm = LLMSettings(
        provider=llm_provider,
        model=llm_model,
        request_timeout_seconds=_env_positive_int("LLM_REQUEST_TIMEOUT_SECONDS", 180),
    )
    product = ProductSettings(
        homepage_recent_hours=_env_positive_int("PRODUCT_HOMEPAGE_RECENT_HOURS", 48),
        homepage_default_limit=_env_positive_int("PRODUCT_HOMEPAGE_DEFAULT_LIMIT", 20),
        homepage_max_limit=_env_positive_int("PRODUCT_HOMEPAGE_MAX_LIMIT", 100),
        homepage_min_recent_items=_env_positive_int("PRODUCT_HOMEPAGE_MIN_RECENT_ITEMS", 8),
        homepage_backfill_days=_env_optional_positive_int("PRODUCT_HOMEPAGE_BACKFILL_DAYS", 7),
    )
    daily_pipeline = DailyPipelineSettings(
        source_group=os.getenv("DAILY_PIPELINE_SOURCE_GROUP", "daily_all"),
        lookback_hours=_env_positive_int("DAILY_PIPELINE_LOOKBACK_HOURS", 8),
        candidate_lookback_hours=_env_positive_int("DAILY_PIPELINE_CANDIDATE_LOOKBACK_HOURS", 48),
        selector_batch_size=_env_positive_int("DAILY_PIPELINE_SELECTOR_BATCH_SIZE", 30),
        max_selected=_env_optional_positive_int("DAILY_PIPELINE_MAX_SELECTED", 5),
        continue_on_source_error=_env_bool("DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR", True),
        disable_agent_fallback=_env_bool("DAILY_PIPELINE_DISABLE_AGENT_FALLBACK", True),
    )
    scheduler = SchedulerSettings(
        timezone=_env_timezone("SCHEDULER_TIMEZONE", "Asia/Shanghai"),
        daily_pipeline_times=_env_schedule_times("SCHEDULER_DAILY_PIPELINE_TIMES", ("08:00", "13:00", "20:00")),
    )
    return Settings(
        runtime=runtime,
        llm=llm,
        product=product,
        daily_pipeline=daily_pipeline,
        scheduler=scheduler,
        agent_mode=os.getenv("AGENT_MODE", "llm"),
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


def _env_positive_int(name: str, default: int) -> int:
    """读取必须为正整数的配置。"""
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _env_optional_positive_int(name: str, default: int | None) -> int | None:
    """读取可用 0 表示不限制的正整数配置。"""
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer or 0") from exc
    if value == 0:
        return None
    if value < 0:
        raise ValueError(f"{name} must be a positive integer or 0")
    return value


def _env_bool(name: str, default: bool) -> bool:
    """读取严格布尔配置。"""
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _env_timezone(name: str, default: str) -> str:
    """读取并校验时区配置。"""
    value = (os.getenv(name) or default).strip()
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"{name} must be a valid timezone") from exc
    return value


def _env_schedule_times(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """读取并校验 HH:MM 调度时间列表。"""
    raw_value = os.getenv(name)
    values = default if raw_value is None or raw_value.strip() == "" else tuple(
        part.strip() for part in raw_value.split(",") if part.strip()
    )
    if not values:
        raise ValueError(f"{name} must contain at least one HH:MM value")
    for value in values:
        parts = value.split(":", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"{name} values must use HH:MM")
        hour, minute = parts
        if len(hour) != 2 or len(minute) != 2 or not hour.isdigit() or not minute.isdigit():
            raise ValueError(f"{name} values must use HH:MM")
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError(f"{name} values must use valid HH:MM times")
    return values
