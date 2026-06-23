from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


def test_smoke_env_connectivity_checks_database_without_leaking_env_values(tmp_path):
    """验证环境自检脚本能读取指定 .env 并连接数据库。

    输入：临时 .env 文件，包含 SQLite DATABASE_URL 和 fake OpenAI 配置。
    输出：脚本返回 succeeded，stdout 不包含原始 database_url 或 API key。
    """
    db_path = tmp_path / "env_smoke.sqlite"
    env_file = tmp_path / ".env"
    database_url = f"sqlite+pysqlite:///{db_path}"
    fake_api_key = "test-openai-key"
    env_file.write_text(
        "\n".join(
            [
                f"DATABASE_URL={database_url}",
                "LLM_PROVIDER=openai",
                "LLM_MODEL=gpt-test",
                f"OPENAI_API_KEY={fake_api_key}",
                "OPENAI_BASE_URL=https://example.test/v1",
                "AGENT_MODE=llm",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_env_connectivity.py",
            "--env-file",
            str(env_file),
            "--create-schema-for-smoke",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "succeeded"
    assert summary["env_loaded"] is True
    assert summary["database_connected"] is True
    assert summary["llm_provider"] == "openai"
    assert summary["llm_model"] == "gpt-test"
    assert summary["api_key_present"] is True
    assert summary["llm_called"] is False
    assert database_url not in result.stdout
    assert fake_api_key not in result.stdout


def test_smoke_env_connectivity_requires_explicit_flag_for_real_llm_call(tmp_path):
    """验证默认自检不会误触发真实 LLM 调用。

    输入：临时 .env 文件和未设置 --call-llm 的命令。
    输出：stdout 标记 llm_called=false，避免普通 smoke 产生真实调用成本。
    """
    db_path = tmp_path / "env_smoke_no_llm.sqlite"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"DATABASE_URL=sqlite+pysqlite:///{db_path}",
                "LLM_PROVIDER=openai",
                "LLM_MODEL=gpt-test",
                "OPENAI_API_KEY=test-openai-key",
                "OPENAI_BASE_URL=https://example.test/v1",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_env_connectivity.py",
            "--env-file",
            str(env_file),
            "--create-schema-for-smoke",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["llm_called"] is False
    assert summary["llm_response_ok"] is None


def test_smoke_env_connectivity_can_require_project_env_file(tmp_path):
    """验证严格项目自洽模式会要求 .env 文件真实存在。

    输入：不存在的 env-file 路径和 --require-env-file。
    输出：脚本失败，明确标记 env_loaded=false，避免误用当前 shell 上下文环境。
    """
    missing_env_file = tmp_path / ".env"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_env_connectivity.py",
            "--env-file",
            str(missing_env_file),
            "--require-env-file",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    summary = json.loads(result.stdout)
    assert summary["status"] == "failed"
    assert summary["env_loaded"] is False
    assert summary["error_type"] == "FileNotFoundError"


@pytest.mark.network
def test_real_project_env_connectivity_when_explicitly_enabled():
    """显式开启时，验证项目根 .env 能同时完成数据库连接和真实 LLM 调用。

    输入：当前 worktree 项目根 `.env`，以及 AI_WORLD_RADAR_RUN_REAL_ENV_SMOKE=1。
    输出：数据库连接成功，真实 LLM 返回 pong；未显式开启时跳过，避免 CI 或普通回归误调用真实服务。
    """
    if os.getenv("AI_WORLD_RADAR_RUN_REAL_ENV_SMOKE") != "1":
        pytest.skip("Set AI_WORLD_RADAR_RUN_REAL_ENV_SMOKE=1 to call real LLM and database from project .env.")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_env_connectivity.py",
            "--call-llm",
            "--require-env-file",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "succeeded"
    assert summary["env_loaded"] is True
    assert summary["database_connected"] is True
    assert summary["llm_called"] is True
    assert summary["llm_response_ok"] is True
