import json
import sqlite3
import subprocess
import sys


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
