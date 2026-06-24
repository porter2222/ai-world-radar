from __future__ import annotations

import json


def test_run_daily_pipeline_script_reads_project_env_and_prints_summary(monkeypatch, tmp_path, capsys):
    """验证一键日常 pipeline CLI 能读取指定 `.env` 并打印漏斗摘要。

    输入：临时 `.env`、SQLite DATABASE_URL 和 fake DailyPipelineService。
    输出：main 返回 0，stdout JSON 包含 fake service 产生的 summary。
    """
    from scripts import run_daily_pipeline

    database_url = f"sqlite+pysqlite:///{tmp_path / 'daily_pipeline.sqlite'}"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"DATABASE_URL={database_url}",
                "AGENT_MODE=llm",
                "LLM_PROVIDER=openai",
                "LLM_MODEL=gpt-test",
                "OPENAI_API_KEY=test-openai-key",
                "DAILY_PIPELINE_SOURCE_GROUP=daily_all",
                "DAILY_PIPELINE_LOOKBACK_HOURS=8",
                "DAILY_PIPELINE_SELECTOR_BATCH_SIZE=30",
                "DAILY_PIPELINE_MAX_SELECTED=2",
                "DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR=true",
                "DAILY_PIPELINE_DISABLE_AGENT_FALLBACK=true",
            ]
        ),
        encoding="utf-8",
    )

    class FakeDailyPipelineService:
        """替代真实 service，避免单元测试访问外部来源或 LLM。

        输入：CLI 创建的 Session。
        输出：run_once 返回稳定 summary。
        """

        def __init__(self, session):
            """记录 CLI 传入的 Session。

            输入：SQLAlchemy Session。
            输出：可调用 run_once 的 fake service。
            """
            self.session = session

        def run_once(self, config):
            """返回可断言的漏斗 summary。

            输入：DailyPipelineConfig。
            输出：包含从 `.env` 读取配置值的 summary。
            """
            return {
                "status": "succeeded",
                "agent_mode": config.agent_mode,
                "source_group": config.source_group,
                "max_selected": config.max_selected,
                "raw_new_signals_count": 3,
                "candidate_groups_count": 3,
                "selector_selected_count": 2,
                "published_count": 2,
            }

    monkeypatch.setattr(run_daily_pipeline, "DailyPipelineService", FakeDailyPipelineService)

    exit_code = run_daily_pipeline.main(["--env-file", str(env_file)])
    stdout = capsys.readouterr().out
    summary = json.loads(stdout)

    assert exit_code == 0
    assert summary["status"] == "succeeded"
    assert summary["agent_mode"] == "llm"
    assert summary["source_group"] == "daily_all"
    assert summary["max_selected"] == 2
    assert summary["published_count"] == 2


def test_run_daily_pipeline_script_does_not_print_database_url_or_api_key(monkeypatch, tmp_path, capsys):
    """验证一键日常 pipeline CLI 不把敏感配置打印到 stdout。

    输入：包含 DATABASE_URL 和 OPENAI_API_KEY 的临时 `.env`。
    输出：stdout JSON 不包含原始数据库连接串或 API key。
    """
    from scripts import run_daily_pipeline

    database_url = f"sqlite+pysqlite:///{tmp_path / 'secret_daily_pipeline.sqlite'}"
    api_key = "test-secret-openai-key"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"DATABASE_URL={database_url}",
                "AGENT_MODE=llm",
                "LLM_PROVIDER=openai",
                "LLM_MODEL=gpt-test",
                f"OPENAI_API_KEY={api_key}",
            ]
        ),
        encoding="utf-8",
    )

    class FakeDailyPipelineService:
        """返回最小成功 summary 的测试 service。

        输入：CLI 创建的 Session。
        输出：不包含敏感配置的 summary。
        """

        def __init__(self, session):
            """初始化 fake service。

            输入：SQLAlchemy Session。
            输出：可运行的 fake service。
            """
            self.session = session

        def run_once(self, config):
            """返回最小成功结果。

            输入：DailyPipelineConfig。
            输出：只包含公开漏斗字段的 summary。
            """
            return {"status": "no_new_signals", "published_count": 0, "agent_mode": config.agent_mode}

    monkeypatch.setattr(run_daily_pipeline, "DailyPipelineService", FakeDailyPipelineService)

    exit_code = run_daily_pipeline.main(["--env-file", str(env_file)])
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(stdout)["status"] == "no_new_signals"
    assert database_url not in stdout
    assert api_key not in stdout
