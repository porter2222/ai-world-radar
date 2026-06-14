import json
import sqlite3
import subprocess
import sys


def query_counts(db_path):
    """查询采集脚本 smoke 数据库计数。

    输入：SQLite 数据库文件路径。
    输出：sources、source_signals、pipeline_runs、published_events 的行数。
    """
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        return {
            "sources": cursor.execute("select count(*) from sources").fetchone()[0],
            "source_signals": cursor.execute("select count(*) from source_signals").fetchone()[0],
            "pipeline_runs": cursor.execute("select count(*) from pipeline_runs").fetchone()[0],
            "published_events": cursor.execute("select count(*) from published_events").fetchone()[0],
        }
    finally:
        connection.close()


def test_collect_source_signals_script_writes_fixture_signals_without_running_pipeline(tmp_path):
    """验证采集脚本只写来源和信号，不运行事件生产 workflow。

    输入：临时 SQLite、fixture 模式、HN source 和 GitHub source。
    输出：stdout 返回 signals_count=4，数据库有 source_signals，但没有 pipeline_runs / published_events。
    """
    db_path = tmp_path / "p1_3_collect_fixture.sqlite"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_source_signals.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--create-schema-for-smoke",
            "--fixture-mode",
            "--source",
            "hn",
            "--hn-limit",
            "2",
            "--source",
            "github",
            "--github-repo",
            "openai/openai-python",
            "--github-limit",
            "2",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    counts = query_counts(db_path)
    assert summary["status"] == "succeeded"
    assert summary["sources_count"] == 2
    assert summary["signals_count"] == 4
    assert summary["source_keys"] == ["github_releases", "hn_algolia"]
    assert counts == {"sources": 2, "source_signals": 4, "pipeline_runs": 0, "published_events": 0}


def test_collect_source_signals_script_upserts_fixture_signals_idempotently(tmp_path):
    """验证采集脚本重复运行不会重复写入同一批信号。

    输入：同一个临时 SQLite 数据库和两次完全相同的 fixture 采集命令。
    输出：第二次 stdout 仍返回 signals_count=4，数据库 source_signals 行数保持 4。
    """
    db_path = tmp_path / "p1_3_collect_idempotent.sqlite"
    command = [
        sys.executable,
        "scripts/collect_source_signals.py",
        "--database-url",
        f"sqlite+pysqlite:///{db_path}",
        "--create-schema-for-smoke",
        "--fixture-mode",
        "--source",
        "hn",
        "--hn-limit",
        "2",
        "--source",
        "github",
        "--github-repo",
        "openai/openai-python",
        "--github-limit",
        "2",
    ]

    first = subprocess.run(command, check=False, text=True, capture_output=True)
    second = subprocess.run(command, check=False, text=True, capture_output=True)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["signals_count"] == 4
    assert query_counts(db_path)["source_signals"] == 4
