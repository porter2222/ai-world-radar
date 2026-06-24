from worker.config import load_settings


def test_load_settings_defaults_to_openai_provider_when_env_missing(monkeypatch, tmp_path):
    """验证未显式配置 LLM 时默认使用 OpenAI 和真实 LLM Agent 模式。

    输入：没有 `.env` 的临时项目根目录，并清空 LLM_PROVIDER / LLM_MODEL。
    输出：settings.llm_provider 为 openai，settings.llm_model 为 gpt-4o-mini，settings.agent_mode 为 llm。
    """
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("AGENT_MODE", raising=False)

    settings = load_settings()

    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.agent_mode == "llm"


def test_env_example_contains_local_runtime_closure_keys():
    """验证 `.env.example` 覆盖本地闭环运行所需的配置项。

    输入：项目根目录 `.env.example`。
    输出：模板包含数据库、OpenAI、Agent、采集和本地 API 配置键，且不包含真实密钥占位以外的敏感值。
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
        "DAILY_PIPELINE_SOURCE_GROUP",
        "DAILY_PIPELINE_LOOKBACK_HOURS",
        "DAILY_PIPELINE_SELECTOR_BATCH_SIZE",
        "DAILY_PIPELINE_MAX_SELECTED",
        "DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR",
        "DAILY_PIPELINE_DISABLE_AGENT_FALLBACK",
        "AI_WORLD_RADAR_API_BASE_URL",
    }

    present_keys = {
        line.split("=", maxsplit=1)[0].strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }

    assert required_keys <= present_keys
    assert "sk-" not in content
    assert "cjy2037388336" not in content
