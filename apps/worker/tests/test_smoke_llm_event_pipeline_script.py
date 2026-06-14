import json
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
