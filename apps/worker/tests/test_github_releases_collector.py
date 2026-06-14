import json
from datetime import UTC, datetime
from pathlib import Path

from worker.collectors.github_releases import collect_from_github_releases_payload, parse_github_release
from worker.sources.github_source import build_github_releases_source, github_release_to_signal


FIXTURE = Path(__file__).parent / "fixtures" / "github_releases_response.json"


def load_payload() -> list[dict]:
    """读取 GitHub releases fixture。

    输入：无。
    输出：GitHub REST API releases 风格的 JSON 列表。
    """
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_github_release_maps_required_fields():
    """验证 GitHub release payload 能映射为领域对象。

    输入：fixture 中的第一条 release JSON、owner 和 repo。
    输出：断言 release id、仓库、标题、URL、发布时间、正文和资产数正确。
    """
    release = parse_github_release(load_payload()[0], owner="openai", repo="openai-python")

    assert release.release_id == "2001"
    assert release.owner == "openai"
    assert release.repo == "openai-python"
    assert release.tag_name == "v1.2.0"
    assert release.name == "OpenAI Python v1.2.0"
    assert release.html_url == "https://github.com/openai/openai-python/releases/tag/v1.2.0?utm_source=hn#assets"
    assert release.published_at == datetime(2026, 6, 10, 9, 0, tzinfo=UTC)
    assert release.body == "Adds Responses API helper improvements and bug fixes."
    assert release.assets_count == 2
    assert release.is_prerelease is False
    assert release.is_draft is False


def test_collect_from_github_releases_payload_sorts_by_published_at_descending():
    """验证 releases payload 会按发布时间倒序并限制数量。

    输入：包含两条 release 的 fixture payload。
    输出：断言最新 prerelease 排在第一位，limit=1 时只返回一条。
    """
    releases = collect_from_github_releases_payload(load_payload(), owner="openai", repo="openai-python", limit=1)

    assert [release.release_id for release in releases] == ["2002"]
    assert releases[0].tag_name == "v1.3.0b1"
    assert releases[0].name == ""


def test_github_release_maps_to_source_signal_create():
    """验证 GitHubRelease 能映射为 SourceSignalCreate。

    输入：fixture 中的第一条 release。
    输出：断言 source_hash、canonical_url、raw_summary、heat_metrics 和 metadata 符合 P1-3 口径。
    """
    source = build_github_releases_source()
    release = parse_github_release(load_payload()[0], owner="openai", repo="openai-python")
    signal = github_release_to_signal(release)

    assert source.source_key == "github_releases"
    assert source.source_type == "code_hosting"
    assert source.fetch_method == "api"
    assert signal.source_key == "github_releases"
    assert signal.source_item_id == "openai/openai-python#2001"
    assert signal.source_hash == "github_releases:openai/openai-python:2001"
    assert signal.original_title == "openai/openai-python released OpenAI Python v1.2.0"
    assert signal.original_url == "https://github.com/openai/openai-python/releases/tag/v1.2.0?utm_source=hn#assets"
    assert signal.canonical_url == "https://github.com/openai/openai-python/releases/tag/v1.2.0"
    assert signal.published_at == datetime(2026, 6, 10, 9, 0, tzinfo=UTC)
    assert signal.raw_summary == "Adds Responses API helper improvements and bug fixes."
    assert signal.heat_metrics == {"assets_count": 2, "is_prerelease": False, "is_draft": False}
    assert signal.metadata["owner"] == "openai"
    assert signal.metadata["repo"] == "openai-python"
    assert signal.metadata["tag_name"] == "v1.2.0"
