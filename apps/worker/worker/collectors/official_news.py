from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup


OfficialSourceMode = Literal["rss", "atom", "html"]


@dataclass(frozen=True)
class OfficialSourceProfile:
    """官方来源配置的规范化结构。

    输入：官方源 key、名称、采集模式和入口 URL。
    输出：供 collector 和 source adapter 共用的稳定 profile 对象。
    """

    source_key: str
    name: str
    mode: OfficialSourceMode
    entry_url: str


@dataclass(frozen=True)
class OfficialNewsEntry:
    """官方新闻条目的规范化结构。

    输入：RSS item、Atom entry 或 HTML 列表项解析后的基础字段。
    输出：供 official_news_source 映射 SourceSignalCreate 的稳定数据对象。
    """

    profile: OfficialSourceProfile
    entry_id: str
    title: str
    url: str
    published_at: datetime | None
    summary: str | None


def collect_from_feed_xml(xml: str, *, profile: OfficialSourceProfile, limit: int) -> list[OfficialNewsEntry]:
    """从 RSS 或 Atom XML 中提取官方新闻条目。

    输入：feed XML 文本、官方来源 profile 和最大条目数。
    输出：按 feed 原始顺序截断后的 OfficialNewsEntry 列表。
    """
    root = ElementTree.fromstring(xml)
    if _strip_namespace(root.tag) == "rss":
        return _collect_from_rss_root(root, profile=profile, limit=limit)
    if _strip_namespace(root.tag) == "feed":
        return _collect_from_atom_root(root, profile=profile, limit=limit)
    raise ValueError(f"Unsupported official feed root: {_strip_namespace(root.tag)}")


def collect_from_news_html(html: str, *, profile: OfficialSourceProfile, limit: int) -> list[OfficialNewsEntry]:
    """从官网轻量 HTML 列表页中提取官方新闻条目。

    输入：列表页 HTML 文本、官方来源 profile 和最大条目数。
    输出：只基于当前列表页解析出的 OfficialNewsEntry 列表，不跟进详情页。
    """
    soup = BeautifulSoup(html, "html.parser")
    entries: list[OfficialNewsEntry] = []

    for article in soup.find_all("article"):
        link = article.find("a", href=True)
        title_node = article.find(["h1", "h2", "h3"])
        if link is None or title_node is None:
            continue

        absolute_url = urljoin(profile.entry_url, str(link["href"]))
        time_node = article.find("time")
        summary_node = article.find("p")
        entries.append(
            OfficialNewsEntry(
                profile=profile,
                entry_id=absolute_url,
                title=_clean_text(title_node.get_text(" ", strip=True)),
                url=absolute_url,
                published_at=_parse_datetime(time_node.get("datetime") if time_node else None),
                summary=_clean_optional_text(summary_node.get_text(" ", strip=True) if summary_node else None),
            )
        )
        if len(entries) >= limit:
            break

    return entries


def fetch_official_news(profile: OfficialSourceProfile, limit: int = 5) -> list[OfficialNewsEntry]:
    """请求官方来源并返回新闻条目列表。

    输入：官方来源 profile 和最大条目数。
    输出：按 profile.mode 解析后的 OfficialNewsEntry 列表；网络错误由 httpx 抛出。
    """
    with httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": "ai-world-radar-worker"}) as client:
        response = client.get(profile.entry_url)
        response.raise_for_status()
        text = response.text

    if profile.mode in {"rss", "atom"}:
        return collect_from_feed_xml(text, profile=profile, limit=limit)
    if profile.mode == "html":
        return collect_from_news_html(text, profile=profile, limit=limit)
    raise ValueError(f"Unsupported official source mode: {profile.mode}")


def _collect_from_rss_root(
    root: ElementTree.Element,
    *,
    profile: OfficialSourceProfile,
    limit: int,
) -> list[OfficialNewsEntry]:
    """从 RSS root 中提取 item 列表。

    输入：ElementTree RSS root、官方来源 profile 和最大条目数。
    输出：OfficialNewsEntry 列表。
    """
    channel = root.find("channel")
    if channel is None:
        return []

    entries: list[OfficialNewsEntry] = []
    for item in channel.findall("item"):
        title = _find_text(item, "title")
        url = _find_text(item, "link")
        if not title or not url:
            continue
        entry_id = _find_text(item, "guid") or url
        entries.append(
            OfficialNewsEntry(
                profile=profile,
                entry_id=entry_id,
                title=title,
                url=url,
                published_at=_parse_datetime(_find_text(item, "pubDate")),
                summary=_find_text(item, "description"),
            )
        )
        if len(entries) >= limit:
            break
    return entries


def _collect_from_atom_root(
    root: ElementTree.Element,
    *,
    profile: OfficialSourceProfile,
    limit: int,
) -> list[OfficialNewsEntry]:
    """从 Atom root 中提取 entry 列表。

    输入：ElementTree Atom root、官方来源 profile 和最大条目数。
    输出：OfficialNewsEntry 列表。
    """
    entries: list[OfficialNewsEntry] = []
    for entry in _findall_by_local_name(root, "entry"):
        title = _find_child_text_by_local_name(entry, "title")
        url = _find_atom_link(entry)
        if not title or not url:
            continue
        entry_id = _find_child_text_by_local_name(entry, "id") or url
        entries.append(
            OfficialNewsEntry(
                profile=profile,
                entry_id=entry_id,
                title=title,
                url=url,
                published_at=_parse_datetime(
                    _find_child_text_by_local_name(entry, "updated")
                    or _find_child_text_by_local_name(entry, "published")
                ),
                summary=_find_child_text_by_local_name(entry, "summary"),
            )
        )
        if len(entries) >= limit:
            break
    return entries


def _find_text(parent: ElementTree.Element, tag_name: str) -> str | None:
    """读取 XML 子节点文本。

    输入：父节点和直接子节点名称。
    输出：清洗后的文本；节点不存在或文本为空时返回 None。
    """
    node = parent.find(tag_name)
    return _clean_optional_text(node.text if node is not None else None)


def _findall_by_local_name(parent: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
    """按忽略命名空间的 local name 查找子节点。

    输入：父节点和目标 local name。
    输出：匹配的直接子节点列表。
    """
    return [child for child in list(parent) if _strip_namespace(child.tag) == local_name]


def _find_child_text_by_local_name(parent: ElementTree.Element, local_name: str) -> str | None:
    """按 local name 读取 XML 子节点文本。

    输入：父节点和目标 local name。
    输出：清洗后的文本；不存在时返回 None。
    """
    for child in list(parent):
        if _strip_namespace(child.tag) == local_name:
            return _clean_optional_text(child.text)
    return None


def _find_atom_link(entry: ElementTree.Element) -> str | None:
    """读取 Atom entry 的 alternate link。

    输入：Atom entry 节点。
    输出：优先返回 rel=alternate 的 href；否则返回第一条 link href；没有 link 时返回 None。
    """
    fallback: str | None = None
    for child in list(entry):
        if _strip_namespace(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if not href:
            continue
        if fallback is None:
            fallback = href
        if child.attrib.get("rel", "alternate") == "alternate":
            return href
    return fallback


def _strip_namespace(tag: str) -> str:
    """移除 XML tag 的命名空间。

    输入：可能包含 `{namespace}` 前缀的 tag。
    输出：不带命名空间的 local name。
    """
    return tag.rsplit("}", maxsplit=1)[-1]


def _parse_datetime(value: str | None) -> datetime | None:
    """解析官方源常见时间格式。

    输入：RSS pubDate、ISO datetime 或日期字符串。
    输出：timezone-aware datetime；空值返回 None。
    """
    if not value:
        return None
    raw_value = value.strip()
    try:
        parsed = parsedate_to_datetime(raw_value)
    except (TypeError, ValueError):
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _clean_text(value: str) -> str:
    """清洗必填文本。

    输入：原始文本。
    输出：压缩空白后的文本。
    """
    return " ".join(value.split())


def _clean_optional_text(value: str | None) -> str | None:
    """清洗可选文本。

    输入：可能为空的原始文本。
    输出：压缩空白后的文本；空输入或空白输入返回 None。
    """
    if value is None:
        return None
    cleaned = _clean_text(value)
    return cleaned or None
