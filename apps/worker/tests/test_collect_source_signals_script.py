import json
import sqlite3
import subprocess
import sys

from scripts.collect_source_signals import get_official_source_profile


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


def query_signals(db_path):
    """查询采集脚本写入的来源信号明细。
    输入：SQLite 数据库文件路径。
    输出：按 source_hash 排序后的信号列表，包含来源 key、hash、热度指标和 metadata。
    """
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        rows = cursor.execute(
            """
            select
                sources.source_key,
                source_signals.source_item_id,
                source_signals.source_hash,
                source_signals.heat_metrics,
                source_signals.metadata
            from source_signals
            join sources on sources.id = source_signals.source_id
            order by source_signals.source_hash
            """
        ).fetchall()
        return [
            {
                "source_key": row["source_key"],
                "source_item_id": row["source_item_id"],
                "source_hash": row["source_hash"],
                "heat_metrics": json.loads(row["heat_metrics"]),
                "metadata": json.loads(row["metadata"]),
            }
            for row in rows
        ]
    finally:
        connection.close()


def set_signal_stars(db_path, *, source_hash, stars):
    """修改测试数据库中某条 signal 的 star 快照。
    输入：SQLite 数据库路径、目标 source_hash 和要写入的 star 数。
    输出：无返回值；用于准备“上一轮快照比当前更低”的脚本回归场景。
    """
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        raw_metrics = cursor.execute(
            "select heat_metrics from source_signals where source_hash = ?",
            (source_hash,),
        ).fetchone()[0]
        metrics = json.loads(raw_metrics)
        metrics["stargazers_count"] = stars
        cursor.execute(
            "update source_signals set heat_metrics = ? where source_hash = ?",
            (json.dumps(metrics), source_hash),
        )
        connection.commit()
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


def test_collect_source_signals_script_writes_github_trends_fixture_without_running_pipeline(tmp_path):
    """验证 GitHub repo trends fixture 采集只写 source_signals。
    输入：临时 SQLite、fixture 模式、github_trends source、固定 query 和 snapshot bucket。
    输出：stdout 返回 github_repo_trends，数据库只新增来源信号，不新增 pipeline_runs / published_events。
    """
    db_path = tmp_path / "p1_7_github_trends_collect.sqlite"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_source_signals.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--create-schema-for-smoke",
            "--fixture-mode",
            "--source",
            "github_trends",
            "--github-trend-query",
            "topic:llm stars:>100",
            "--github-trend-limit",
            "1",
            "--github-trend-min-stars",
            "100",
            "--snapshot-bucket",
            "2026062311",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)
    counts = query_counts(db_path)
    signals = query_signals(db_path)

    assert summary["status"] == "succeeded"
    assert summary["source_keys"] == ["github_repo_trends"]
    assert summary["sources_count"] == 1
    assert summary["signals_count"] == 1
    assert counts == {"sources": 1, "source_signals": 1, "pipeline_runs": 0, "published_events": 0}
    assert signals[0]["source_key"] == "github_repo_trends"
    assert signals[0]["source_item_id"] == "example/fast-llm"
    assert signals[0]["source_hash"] == "github_repo_trends:example/fast-llm:2026062311"
    assert signals[0]["heat_metrics"]["stargazers_count"] == 1250
    assert signals[0]["heat_metrics"]["stars_delta_since_last"] is None
    assert signals[0]["metadata"]["query"] == "topic:llm stars:>100"
    assert signals[0]["metadata"]["snapshot_bucket"] == "2026062311"


def test_collect_source_signals_script_calculates_github_trend_delta_from_previous_snapshot(tmp_path):
    """验证 GitHub repo trends 二次采集会读取上一轮星数计算增量。
    输入：同一 SQLite，先写入旧 bucket 并把旧快照 star 数设为 1000，再运行 fixture 采集新 bucket。
    输出：第二条 signal 的 `stars_delta_since_last=250`，采集脚本仍不运行发布 pipeline。
    """
    db_path = tmp_path / "p1_7_github_trends_delta.sqlite"
    seed = subprocess.run(
        [
            sys.executable,
            "scripts/collect_source_signals.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--create-schema-for-smoke",
            "--fixture-mode",
            "--source",
            "github_trends",
            "--github-trend-query",
            "topic:llm stars:>100",
            "--github-trend-limit",
            "1",
            "--github-trend-min-stars",
            "100",
            "--snapshot-bucket",
            "2026062310",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert seed.returncode == 0, seed.stderr or seed.stdout
    set_signal_stars(
        db_path,
        source_hash="github_repo_trends:example/fast-llm:2026062310",
        stars=1000,
    )
    current = subprocess.run(
        [
            sys.executable,
            "scripts/collect_source_signals.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--fixture-mode",
            "--source",
            "github_trends",
            "--github-trend-query",
            "topic:llm stars:>100",
            "--github-trend-limit",
            "1",
            "--github-trend-min-stars",
            "100",
            "--snapshot-bucket",
            "2026062311",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert current.returncode == 0, current.stderr or current.stdout
    summary = json.loads(current.stdout)
    counts = query_counts(db_path)
    signals = query_signals(db_path)
    latest_signal = next(signal for signal in signals if signal["source_hash"].endswith(":2026062311"))

    assert summary["source_keys"] == ["github_repo_trends"]
    assert counts == {"sources": 1, "source_signals": 2, "pipeline_runs": 0, "published_events": 0}
    assert latest_signal["heat_metrics"]["previous_stargazers_count"] == 1000
    assert latest_signal["heat_metrics"]["stars_delta_since_last"] == 250
    assert latest_signal["heat_metrics"]["stars_delta_rate"] == 0.25


def test_collect_source_signals_script_writes_official_feeds_fixture_without_running_pipeline(tmp_path):
    """验证官方源 fixture 采集只写 source_signals。
    输入：临时 SQLite、fixture 模式、official_feeds source 和 nvidia_news profile。
    输出：stdout 返回 nvidia_news，数据库只新增官方来源信号，不新增 pipeline_runs / published_events。
    """
    db_path = tmp_path / "p1_7_official_feeds_collect.sqlite"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_source_signals.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--create-schema-for-smoke",
            "--fixture-mode",
            "--source",
            "official_feeds",
            "--official-profile",
            "nvidia_news",
            "--official-limit",
            "1",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)
    counts = query_counts(db_path)
    signals = query_signals(db_path)

    assert summary["status"] == "succeeded"
    assert summary["source_keys"] == ["nvidia_news"]
    assert summary["sources_count"] == 1
    assert summary["signals_count"] == 1
    assert counts == {"sources": 1, "source_signals": 1, "pipeline_runs": 0, "published_events": 0}
    assert signals[0]["source_key"] == "nvidia_news"
    assert signals[0]["source_item_id"] == "nvidia-ai-factory-2026"
    assert signals[0]["heat_metrics"]["official_source"] is True
    assert signals[0]["metadata"]["source"] == "official_news"
    assert signals[0]["metadata"]["profile_key"] == "nvidia_news"
    assert signals[0]["metadata"]["mode"] == "rss"


def test_collect_source_signals_script_combines_github_trends_and_official_feeds(tmp_path):
    """验证采集脚本可以组合 GitHub trends 与官方源。
    输入：临时 SQLite、fixture 模式、github_trends 和 official_feeds 两类 source。
    输出：stdout 返回两个 source_key，数据库只有 source_signals，没有事件生产表写入。
    """
    db_path = tmp_path / "p1_7_combined_sources_collect.sqlite"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_source_signals.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--create-schema-for-smoke",
            "--fixture-mode",
            "--source",
            "github_trends",
            "--github-trend-query",
            "topic:llm stars:>100",
            "--github-trend-limit",
            "1",
            "--snapshot-bucket",
            "2026062311",
            "--source",
            "official_feeds",
            "--official-profile",
            "nvidia_news",
            "--official-limit",
            "1",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)
    counts = query_counts(db_path)
    signals = query_signals(db_path)

    assert summary["status"] == "succeeded"
    assert summary["source_keys"] == ["github_repo_trends", "nvidia_news"]
    assert summary["sources_count"] == 2
    assert summary["signals_count"] == 2
    assert counts == {"sources": 2, "source_signals": 2, "pipeline_runs": 0, "published_events": 0}
    assert {signal["source_key"] for signal in signals} == {"github_repo_trends", "nvidia_news"}


def test_nvidia_official_profile_points_to_xml_feed():
    """验证 NVIDIA 官方源 profile 指向实际 XML feed。
    输入：内置 `nvidia_news` profile key。
    输出：entry_url 使用 `/rss.xml`，避免误指向返回 HTML 订阅说明页的 `/rss`。
    """
    profile = get_official_source_profile("nvidia_news")

    assert profile.mode == "rss"
    assert profile.entry_url == "https://nvidianews.nvidia.com/rss.xml"


def test_expanded_official_profiles_point_to_public_rss_feeds():
    """验证 P1-8 首批公开平台源 profile 指向稳定 RSS/XML 地址。
    输入：P1-8 计划中选定的官方与开发者平台 profile key。
    输出：每个 profile 均存在，且 mode 和 entry_url 与真实探测通过的公开 feed 一致。
    """
    expected_profiles = {
        "openai_news": "https://openai.com/news/rss.xml",
        "github_changelog": "https://github.blog/changelog/feed/",
        "huggingface_blog": "https://huggingface.co/blog/feed.xml",
        "google_ai_blog": "https://blog.google/technology/ai/rss/",
        "aws_machine_learning_blog": "https://aws.amazon.com/blogs/machine-learning/feed/",
        "pytorch_blog": "https://pytorch.org/blog/feed.xml",
        "ollama_blog": "https://ollama.com/blog/rss.xml",
    }

    for profile_key, entry_url in expected_profiles.items():
        profile = get_official_source_profile(profile_key)
        assert profile.mode == "rss"
        assert profile.entry_url == entry_url


def test_collect_source_signals_script_writes_multiple_expanded_official_profiles_without_pipeline(tmp_path):
    """验证 P1-8 新增官方源可批量用 fixture 写入 source_signals。
    输入：临时 SQLite、fixture 模式、多个新增 official profile。
    输出：每个 profile 都写入 1 条官方信号，且不创建 pipeline_runs / published_events。
    """
    db_path = tmp_path / "p1_8_expanded_official_profiles.sqlite"
    profiles = ["openai_news", "huggingface_blog", "ollama_blog"]
    command = [
        sys.executable,
        "scripts/collect_source_signals.py",
        "--database-url",
        f"sqlite+pysqlite:///{db_path}",
        "--create-schema-for-smoke",
        "--fixture-mode",
        "--source",
        "official_feeds",
        "--official-limit",
        "1",
    ]
    for profile in profiles:
        command.extend(["--official-profile", profile])

    result = subprocess.run(command, check=False, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)
    counts = query_counts(db_path)
    signals = query_signals(db_path)

    assert summary["status"] == "succeeded"
    assert summary["source_keys"] == sorted(profiles)
    assert summary["sources_count"] == 3
    assert summary["signals_count"] == 3
    assert counts == {"sources": 3, "source_signals": 3, "pipeline_runs": 0, "published_events": 0}
    assert {signal["source_key"] for signal in signals} == set(profiles)
    assert {signal["metadata"]["mode"] for signal in signals} == {"rss"}


def test_collect_source_signals_script_daily_all_group_writes_all_sources_without_pipeline(tmp_path):
    """验证 daily_all 采集组一次覆盖当前全部日常信息源。

    输入：临时 SQLite、fixture 模式、`--source-group daily_all` 和各来源 limit=1。
    输出：写入 13 个 source key 和 13 条 source_signals，不创建 pipeline_runs / published_events。
    """
    db_path = tmp_path / "p1_9_daily_all_collect.sqlite"
    expected_source_keys = [
        "anthropic_news",
        "aws_machine_learning_blog",
        "deepmind_blog",
        "github_changelog",
        "github_releases",
        "github_repo_trends",
        "google_ai_blog",
        "hn_algolia",
        "huggingface_blog",
        "nvidia_news",
        "ollama_blog",
        "openai_news",
        "pytorch_blog",
    ]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_source_signals.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--create-schema-for-smoke",
            "--fixture-mode",
            "--source-group",
            "daily_all",
            "--hn-limit",
            "1",
            "--github-limit",
            "1",
            "--github-trend-limit",
            "1",
            "--official-limit",
            "1",
            "--snapshot-bucket",
            "2026062312",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)
    counts = query_counts(db_path)
    signals = query_signals(db_path)

    assert summary["status"] == "succeeded"
    assert summary["source_keys"] == expected_source_keys
    assert summary["sources_count"] == 13
    assert summary["signals_count"] == 13
    assert counts == {"sources": 13, "source_signals": 13, "pipeline_runs": 0, "published_events": 0}
    assert sorted({signal["source_key"] for signal in signals}) == expected_source_keys
