from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urljoin
import urllib.request
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup


OfficialSourceMode = Literal["rss", "atom", "html"]
OFFICIAL_NEWS_USER_AGENT = "ai-world-radar-worker"


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
    image_url: str | None = None
    fetch_metadata: dict[str, object] = field(default_factory=dict)


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
        image_url = _find_html_image_url(article, base_url=profile.entry_url)
        entries.append(
            OfficialNewsEntry(
                profile=profile,
                entry_id=absolute_url,
                title=_clean_text(title_node.get_text(" ", strip=True)),
                url=absolute_url,
                published_at=_parse_datetime(time_node.get("datetime") if time_node else None),
                summary=_clean_optional_text(summary_node.get_text(" ", strip=True) if summary_node else None),
                image_url=image_url,
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
    text, fetch_metadata = _fetch_official_source_text(profile)

    if profile.mode in {"rss", "atom"}:
        return _attach_fetch_metadata(collect_from_feed_xml(text, profile=profile, limit=limit), fetch_metadata)
    if profile.mode == "html":
        return _attach_fetch_metadata(collect_from_news_html(text, profile=profile, limit=limit), fetch_metadata)
    raise ValueError(f"Unsupported official source mode: {profile.mode}")


def _fetch_official_source_text(profile: OfficialSourceProfile) -> tuple[str, dict[str, object]]:
    """请求官方源文本，并在 httpx 被 403 拦截时使用标准库兜底。

    输入：官方源 profile。
    输出：响应文本和可选抓取元数据；非 403 错误保持原有异常行为。
    """
    with httpx.Client(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": OFFICIAL_NEWS_USER_AGENT},
    ) as client:
        response = client.get(profile.entry_url)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
            text, fallback_metadata = _fetch_official_source_text_with_urllib(
                profile,
                fallback_reason=str(exc),
            )
            return text, fallback_metadata
        return response.text, {}


def _fetch_official_source_text_with_urllib(
    profile: OfficialSourceProfile,
    *,
    fallback_reason: str,
) -> tuple[str, dict[str, object]]:
    """使用 urllib 兜底拉取官方源文本。

    输入：官方源 profile 和触发兜底的主请求失败原因。
    输出：响应文本和 fallback 审计元数据。
    """
    request = urllib.request.Request(profile.entry_url, headers={"User-Agent": OFFICIAL_NEWS_USER_AGENT})
    with urllib.request.urlopen(request, timeout=20.0) as response:
        raw_body = response.read()
        headers = getattr(response, "headers", {})
        charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
        content_type = headers.get("content-type") if hasattr(headers, "get") else None
        text = raw_body.decode(charset or "utf-8", errors="replace")
        return text, {
            "fallback_used": True,
            "primary_fetch_client": "httpx",
            "fetch_client": "urllib",
            "fallback_reason": fallback_reason,
            "fallback_status_code": getattr(response, "status", None),
            "fallback_content_type": content_type,
        }


def _attach_fetch_metadata(
    entries: list[OfficialNewsEntry],
    fetch_metadata: dict[str, object],
) -> list[OfficialNewsEntry]:
    """把抓取层元数据附加到解析出的官方条目。

    输入：官方条目列表和抓取元数据。
    输出：需要记录 fallback 时返回带 metadata 的新条目，否则保持原列表。
    """
    if not fetch_metadata:
        return entries
    return [replace(entry, fetch_metadata=dict(fetch_metadata)) for entry in entries]


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
                image_url=_find_xml_image_url(item, base_url=url),
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
                image_url=_find_xml_image_url(entry, base_url=url),
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


def _find_xml_image_url(parent: ElementTree.Element, *, base_url: str | None) -> str | None:
    """从 RSS/Atom 条目中提取图片 URL。

    输入：RSS item 或 Atom entry 节点，以及用于补全相对路径的条目 URL。
    输出：media thumbnail/content、image enclosure 或 itunes image 的图片 URL；未找到时返回 None。
    """
    for node in parent.iter():
        if node is parent:
            continue
        local_name = _strip_namespace(node.tag)
        if local_name in {"thumbnail", "content"}:
            image_url = _absolute_image_url(node.attrib.get("url") or node.attrib.get("href"), base_url=base_url)
            media_type = node.attrib.get("type", "")
            medium = node.attrib.get("medium", "")
            if image_url and (local_name == "thumbnail" or medium == "image" or media_type.startswith("image/")):
                return image_url
        if local_name == "enclosure" and node.attrib.get("type", "").startswith("image/"):
            image_url = _absolute_image_url(node.attrib.get("url"), base_url=base_url)
            if image_url:
                return image_url
        if local_name == "image":
            image_url = _absolute_image_url(node.attrib.get("href") or node.attrib.get("url"), base_url=base_url)
            if image_url:
                return image_url
    return None


def _find_html_image_url(article: object, *, base_url: str) -> str | None:
    """从官方 HTML 列表 article 中提取图片 URL。

    输入：BeautifulSoup article 节点和列表页入口 URL。
    输出：首个 img 的 src 或 data-src 绝对地址；没有可用图片时返回 None。
    """
    image_node = article.find("img", src=True) or article.find("img", attrs={"data-src": True})
    if image_node is None:
        return None
    return _absolute_image_url(image_node.get("src") or image_node.get("data-src"), base_url=base_url)


def _absolute_image_url(value: str | None, *, base_url: str | None) -> str | None:
    """清洗并补全图片 URL。

    输入：可能为空、可能为相对路径的图片 URL，以及可选基准 URL。
    输出：可展示的 http(s) 图片 URL；data URL、空值或无法补全时返回 None。
    """
    if not value:
        return None
    raw_value = value.strip()
    if not raw_value or raw_value.startswith("data:"):
        return None
    if base_url:
        raw_value = urljoin(base_url, raw_value)
    if raw_value.startswith("https://") or raw_value.startswith("http://"):
        return raw_value
    return None


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
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None

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
