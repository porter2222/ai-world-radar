import pytest

from worker.config import load_settings


CONFIG_ENV_KEYS = [
    "DATABASE_URL",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_REQUEST_TIMEOUT_SECONDS",
    "AGENT_MODE",
    "PRODUCT_HOMEPAGE_RECENT_HOURS",
    "PRODUCT_HOMEPAGE_DEFAULT_LIMIT",
    "PRODUCT_HOMEPAGE_MAX_LIMIT",
    "PRODUCT_HOMEPAGE_MIN_RECENT_ITEMS",
    "PRODUCT_HOMEPAGE_BACKFILL_DAYS",
    "DAILY_PIPELINE_SOURCE_GROUP",
    "DAILY_PIPELINE_LOOKBACK_HOURS",
    "DAILY_PIPELINE_CANDIDATE_LOOKBACK_HOURS",
    "DAILY_PIPELINE_SELECTOR_BATCH_SIZE",
    "DAILY_PIPELINE_MAX_SELECTED",
    "DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR",
    "DAILY_PIPELINE_DISABLE_AGENT_FALLBACK",
    "SCHEDULER_TIMEZONE",
    "SCHEDULER_DAILY_PIPELINE_TIMES",
]


def clear_config_env(monkeypatch):
    """清空配置相关环境变量，避免本机 .env 或 PowerShell 环境影响默认值测试。"""
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_load_settings_defaults_to_openai_provider_when_env_missing(monkeypatch, tmp_path):
    """验证未显式配置 LLM 时默认使用 OpenAI 和真实 LLM Agent 模式。

    输入：没有 `.env` 的临时项目根目录，并清空 LLM_PROVIDER / LLM_MODEL。
    输出：settings.llm_provider 为 openai，settings.llm_model 为 gpt-4o-mini，settings.agent_mode 为 llm。
    """
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    clear_config_env(monkeypatch)

    settings = load_settings()

    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.agent_mode == "llm"


def test_load_settings_exposes_typed_config_groups(monkeypatch, tmp_path):
    """验证 load_settings 会返回分层 typed config，且默认策略集中在 Settings 内。

    输入：没有 `.env` 的临时项目根目录，并清空配置相关环境变量。
    输出：runtime、llm、product、daily_pipeline、scheduler 均有稳定默认值。
    """
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    clear_config_env(monkeypatch)

    settings = load_settings()

    assert settings.runtime.project_root == tmp_path
    assert settings.runtime.worker_dir == tmp_path / "apps" / "worker"
    assert settings.runtime.runtime_dir == tmp_path / "runtime"
    assert settings.runtime.database_url.startswith("postgresql+psycopg://")
    assert settings.llm.provider == "openai"
    assert settings.llm.model == "gpt-4o-mini"
    assert settings.llm.request_timeout_seconds == 180
    assert settings.agent_mode == "llm"
    assert settings.product.homepage_recent_hours == 48
    assert settings.product.homepage_default_limit == 20
    assert settings.product.homepage_max_limit == 100
    assert settings.product.homepage_min_recent_items == 8
    assert settings.product.homepage_backfill_days == 7
    assert settings.daily_pipeline.source_group == "daily_all"
    assert settings.daily_pipeline.lookback_hours == 8
    assert settings.daily_pipeline.candidate_lookback_hours == 48
    assert settings.daily_pipeline.selector_batch_size == 30
    assert settings.daily_pipeline.max_selected == 5
    assert settings.daily_pipeline.continue_on_source_error is True
    assert settings.daily_pipeline.disable_agent_fallback is True
    assert settings.scheduler.timezone == "Asia/Shanghai"
    assert settings.scheduler.daily_pipeline_times == ("08:00", "13:00", "20:00")


def test_load_settings_keeps_legacy_compatibility_properties(monkeypatch, tmp_path):
    """验证旧调用方仍可读取 Settings 的兼容属性。

    输入：deepseek provider，未显式设置模型。
    输出：旧属性和新分层属性保持一致。
    """
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    clear_config_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    settings = load_settings()

    assert settings.project_root == settings.runtime.project_root
    assert settings.worker_dir == settings.runtime.worker_dir
    assert settings.runtime_dir == settings.runtime.runtime_dir
    assert settings.database_url == settings.runtime.database_url
    assert settings.llm_provider == "deepseek"
    assert settings.llm_model == "deepseek-chat"


def test_load_settings_allows_explicit_env_overrides(monkeypatch, tmp_path):
    """验证允许的本机 override 统一由 load_settings 解析。

    输入：若干 daily pipeline 和 scheduler 环境变量。
    输出：settings.daily_pipeline 和 settings.scheduler 反映显式 override。
    """
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    clear_config_env(monkeypatch)
    monkeypatch.setenv("DAILY_PIPELINE_LOOKBACK_HOURS", "6")
    monkeypatch.setenv("DAILY_PIPELINE_MAX_SELECTED", "0")
    monkeypatch.setenv("DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR", "false")
    monkeypatch.setenv("DAILY_PIPELINE_DISABLE_AGENT_FALLBACK", "yes")
    monkeypatch.setenv("SCHEDULER_DAILY_PIPELINE_TIMES", "09:15,18:45")

    settings = load_settings()

    assert settings.daily_pipeline.lookback_hours == 6
    assert settings.daily_pipeline.max_selected is None
    assert settings.daily_pipeline.continue_on_source_error is False
    assert settings.daily_pipeline.disable_agent_fallback is True
    assert settings.scheduler.daily_pipeline_times == ("09:15", "18:45")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("DAILY_PIPELINE_LOOKBACK_HOURS", "0"),
        ("DAILY_PIPELINE_SELECTOR_BATCH_SIZE", "-1"),
        ("LLM_REQUEST_TIMEOUT_SECONDS", "abc"),
    ],
)
def test_load_settings_rejects_invalid_positive_int(monkeypatch, tmp_path, key, value):
    """验证正整数配置非法时启动早失败。

    输入：非法数字环境变量。
    输出：load_settings 抛出带变量名的 ValueError。
    """
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    clear_config_env(monkeypatch)
    monkeypatch.setenv(key, value)

    with pytest.raises(ValueError, match=key):
        load_settings()


def test_load_settings_rejects_invalid_bool(monkeypatch, tmp_path):
    """验证布尔配置只接受明确值。"""
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    clear_config_env(monkeypatch)
    monkeypatch.setenv("DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR", "maybe")

    with pytest.raises(ValueError, match="DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR"):
        load_settings()


def test_load_settings_rejects_invalid_schedule_time(monkeypatch, tmp_path):
    """验证调度时间必须是合法 HH:MM。"""
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    clear_config_env(monkeypatch)
    monkeypatch.setenv("SCHEDULER_DAILY_PIPELINE_TIMES", "08:00,25:00")

    with pytest.raises(ValueError, match="SCHEDULER_DAILY_PIPELINE_TIMES"):
        load_settings()


def test_env_example_contains_local_runtime_closure_keys():
    """验证 `.env.example` 覆盖本地闭环运行所需的配置项。

    输入：项目根目录 `.env.example`。
    输出：模板包含数据库、OpenAI、Agent 和本地 API 配置键；产品/流水线策略默认值不作为普通模板项。
    """
    env_example = load_settings().project_root / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    required_keys = {
        "DATABASE_URL",
        "AGENT_MODE",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_USER_AGENT",
        "GITHUB_TOKEN",
        "AI_WORLD_RADAR_API_BASE_URL",
    }
    removed_strategy_keys = {
        "DAILY_PIPELINE_SOURCE_GROUP",
        "DAILY_PIPELINE_LOOKBACK_HOURS",
        "DAILY_PIPELINE_SELECTOR_BATCH_SIZE",
        "DAILY_PIPELINE_MAX_SELECTED",
        "DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR",
        "DAILY_PIPELINE_DISABLE_AGENT_FALLBACK",
    }

    present_keys = {
        line.split("=", maxsplit=1)[0].strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }

    assert required_keys <= present_keys
    assert removed_strategy_keys.isdisjoint(present_keys)
    assert "sk-" not in content
    assert "cjy2037388336" not in content
