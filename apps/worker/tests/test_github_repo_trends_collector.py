import json
from datetime import UTC, datetime
from pathlib import Path

from worker.collectors.github_repo_trends import collect_from_github_search_payload, parse_github_repository
from worker.sources.github_trends_source import build_github_repo_trends_source, github_repo_trend_to_signal


FIXTURE = Path(__file__).parent / "fixtures" / "github_repo_search_response.json"


def load_payload() -> dict:
    """读取 GitHub repository search fixture。
    输入：无。
    输出：GitHub Search API repositories 响应风格的 JSON 字典。
    """
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_github_repository_maps_required_fields():
    """验证 GitHub repository payload 能映射为趋势领域对象。
    输入：fixture 中第一条 repository JSON 和命中的搜索 query。
    输出：断言仓库身份、URL、星数、topics、状态和时间字段都被规范化。
    """
    repo = parse_github_repository(load_payload()["items"][0], query="topic:llm stars:>100")

    assert repo.repo_id == "98765001"
    assert repo.owner == "example"
    assert repo.repo == "fast-llm"
    assert repo.full_name == "example/fast-llm"
    assert repo.html_url == "https://github.com/example/fast-llm?utm_source=radar#readme"
    assert repo.description == "A fast local LLM serving runtime for AI agents."
    assert repo.stargazers_count == 1250
    assert repo.forks_count == 120
    assert repo.open_issues_count == 42
    assert repo.language == "Python"
    assert repo.topics == ["llm", "agents", "inference"]
    assert repo.is_fork is False
    assert repo.is_archived is False
    assert repo.pushed_at == datetime(2026, 6, 23, 9, 45, tzinfo=UTC)
    assert repo.updated_at == datetime(2026, 6, 23, 10, 30, tzinfo=UTC)
    assert repo.created_at == datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    assert repo.query == "topic:llm stars:>100"


def test_collect_from_github_search_payload_filters_by_min_stars_and_limit():
    """验证 GitHub Search payload 会按星数阈值过滤并按 limit 截断。
    输入：包含两条仓库的 fixture、min_stars=100 和 limit=1。
    输出：只返回达到阈值的第一条热门仓库趋势对象。
    """
    repos = collect_from_github_search_payload(
        load_payload(),
        query="topic:llm stars:>100",
        limit=1,
        min_stars=100,
    )

    assert [repo.full_name for repo in repos] == ["example/fast-llm"]


def test_github_search_repo_maps_to_trend_signal():
    """验证 GitHub repo trend 能映射为 SourceCreate 和 SourceSignalCreate。
    输入：规范化后的仓库趋势对象、固定 snapshot_bucket 和上一轮星数。
    输出：断言 source_key、source_hash、热度指标、canonical_url 和 metadata 符合 P1-7 口径。
    """
    repo = parse_github_repository(load_payload()["items"][0], query="topic:llm stars:>100")
    source = build_github_repo_trends_source()
    signal = github_repo_trend_to_signal(
        repo,
        snapshot_bucket="2026062311",
        previous_stargazers_count=1000,
    )

    assert source.source_key == "github_repo_trends"
    assert source.name == "GitHub Repo Trends"
    assert source.source_type == "code_hosting"
    assert source.fetch_method == "api"
    assert signal.source_key == "github_repo_trends"
    assert signal.source_item_id == "example/fast-llm"
    assert signal.source_hash == "github_repo_trends:example/fast-llm:2026062311"
    assert signal.original_title == "example/fast-llm is gaining attention on GitHub"
    assert signal.original_url == "https://github.com/example/fast-llm?utm_source=radar#readme"
    assert signal.canonical_url == "https://github.com/example/fast-llm"
    assert signal.published_at == datetime(2026, 6, 23, 9, 45, tzinfo=UTC)
    assert signal.raw_summary == (
        "A fast local LLM serving runtime for AI agents. "
        "GitHub repo with 1250 stars, 120 forks, language Python, topics: llm, agents, inference."
    )
    assert signal.heat_metrics["stargazers_count"] == 1250
    assert signal.heat_metrics["forks_count"] == 120
    assert signal.heat_metrics["open_issues_count"] == 42
    assert signal.heat_metrics["stars_delta_since_last"] == 250
    assert signal.heat_metrics["previous_stargazers_count"] == 1000
    assert signal.heat_metrics["stars_delta_rate"] == 0.25
    assert signal.heat_metrics["is_archived"] is False
    assert signal.heat_metrics["is_fork"] is False
    assert signal.metadata["source"] == "github_repo_trends"
    assert signal.metadata["repo_id"] == "98765001"
    assert signal.metadata["query"] == "topic:llm stars:>100"
    assert signal.metadata["snapshot_bucket"] == "2026062311"


def test_github_search_repo_without_previous_snapshot_has_null_delta():
    """验证首次采集没有历史快照时仍保留冷启动星数。
    输入：规范化后的仓库趋势对象和 previous_stargazers_count=None。
    输出：断言 star delta 与增长率为 None，但总星数仍可用于热度排序。
    """
    repo = parse_github_repository(load_payload()["items"][0], query="topic:llm stars:>100")
    signal = github_repo_trend_to_signal(
        repo,
        snapshot_bucket="2026062311",
        previous_stargazers_count=None,
    )

    assert signal.heat_metrics["stargazers_count"] == 1250
    assert signal.heat_metrics["previous_stargazers_count"] is None
    assert signal.heat_metrics["stars_delta_since_last"] is None
    assert signal.heat_metrics["stars_delta_rate"] is None
