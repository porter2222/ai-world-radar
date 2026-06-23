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
