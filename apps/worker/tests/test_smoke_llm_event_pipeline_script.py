import json
import os
import sqlite3
import subprocess
import sys
import time


def test_smoke_llm_event_pipeline_fixture_mode(tmp_path):
    """验证 fake LLM smoke 脚本首跑即可发布事件。

    输入：临时 SQLite 数据库路径和 --fixture-mode。
    输出：脚本返回 0，stdout JSON 包含 status=succeeded、agent_mode=llm、published_count=1。
    """
    db_path = tmp_path / "p1_4_llm_smoke.sqlite"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_llm_event_pipeline.py",
            "--fixture-mode",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "succeeded"
    assert summary["agent_mode"] == "llm"
    assert summary["published_count"] == 1
    assert summary["agent_runs_count"] == 3
    assert "database_url" not in summary

    connection = sqlite3.connect(db_path)
    try:
        source_key, source_type, entry_url = connection.execute(
            "select source_key, source_type, entry_url from sources"
        ).fetchone()
        original_title, original_url, raw_summary, heat_metrics_json = connection.execute(
            "select original_title, original_url, raw_summary, heat_metrics from source_signals"
        ).fetchone()
    finally:
        connection.close()

    heat_metrics = json.loads(heat_metrics_json)
    assert source_key == "hn_algolia"
    assert source_type == "community"
    assert "news.ycombinator.com" in entry_url
    assert "news.ycombinator.com/item?id=" in original_url
    assert "HN:" in raw_summary
    assert original_title.startswith("HN discussion:")
    assert heat_metrics["points"] >= 300
    assert heat_metrics["comments"] >= 100


def test_smoke_llm_event_pipeline_summary_counts_only_current_run(tmp_path):
    """验证 smoke stdout 统计只统计当前 run，不被同库历史数据污染。

    输入：同一个临时 SQLite 数据库连续运行两次 fixture smoke。
    输出：第二次 stdout 的 agent_runs_count 仍为 3；同 candidate 幂等发布时本轮 published_count 为 0。
    """
    db_path = tmp_path / "p1_4_llm_smoke_twice.sqlite"
    command = [
        sys.executable,
        "scripts/smoke_llm_event_pipeline.py",
        "--fixture-mode",
        "--database-url",
        f"sqlite+pysqlite:///{db_path}",
    ]

    first = subprocess.run(command, check=False, text=True, capture_output=True)
    time.sleep(1.1)
    second = subprocess.run(command, check=False, text=True, capture_output=True)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_summary = json.loads(first.stdout)
    second_summary = json.loads(second.stdout)

    assert first_summary["run_id"] != second_summary["run_id"]
    assert first_summary["published_count"] == 1
    assert second_summary["published_count"] == 0
    assert second_summary["agent_runs_count"] == 3
    assert second_summary["failed_agent_runs_count"] == 0


def test_smoke_llm_event_pipeline_failure_summary_hides_database_url(tmp_path):
    """验证 smoke 失败 stdout 不泄露 database_url。

    输入：缺少真实 provider API key 的 --call-real-provider 命令。
    输出：脚本失败但 JSON 摘要不包含 database_url。
    """
    db_path = tmp_path / "p1_4_llm_smoke_failure.sqlite"
    env = os.environ.copy()
    env["LLM_PROVIDER"] = "openai"
    env.pop("OPENAI_API_KEY", None)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_llm_event_pipeline.py",
            "--call-real-provider",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode != 0
    summary = json.loads(result.stdout)
    assert summary["status"] == "failed"
    assert "database_url" not in summary
