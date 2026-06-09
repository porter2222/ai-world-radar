from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ReadablePage:
    title: str
    text: str
    excerpt: str


@dataclass(frozen=True)
class CachedPage:
    cache_path: Path
    text_hash: str


@dataclass(frozen=True)
class PageFetchResult:
    url: str
    page_title: str | None
    page_excerpt: str | None
    page_text_hash: str | None
    page_cache_path: str | None
    fetch_status: str
    fetched_at: str
    failure_reason: str | None = None


def extract_readable_text(html: str) -> ReadablePage:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    main = soup.find("main") or soup.body or soup
    text = "\n".join(line for line in main.get_text("\n", strip=True).splitlines() if line.strip())
    excerpt = text[:500]
    return ReadablePage(title=title, text=text, excerpt=excerpt)


def build_page_cache_path(runtime_dir: Path, hn_id: str, fetched_date: str | None = None) -> Path:
    fetched_date = fetched_date or datetime.now(UTC).date().isoformat()
    return runtime_dir / "source-pages" / fetched_date / f"hn-{hn_id}-page.txt"


def write_cached_page(cache_path: Path, text: str) -> CachedPage:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text, encoding="utf-8")
    return CachedPage(cache_path=cache_path, text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest())


def fetch_and_cache_url(url: str | None, hn_id: str, runtime_dir: Path, timeout: float = 15.0) -> PageFetchResult:
    fetched_at = datetime.now(UTC).isoformat()
    if not url:
        return PageFetchResult(
            url="",
            page_title=None,
            page_excerpt=None,
            page_text_hash=None,
            page_cache_path=None,
            fetch_status="skipped",
            fetched_at=fetched_at,
            failure_reason="HN story has no original_url",
        )

    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        page = extract_readable_text(response.text)
        cache_path = build_page_cache_path(runtime_dir, hn_id=hn_id)
        cached = write_cached_page(cache_path, page.text)
        return PageFetchResult(
            url=url,
            page_title=page.title,
            page_excerpt=page.excerpt,
            page_text_hash=cached.text_hash,
            page_cache_path=str(cached.cache_path),
            fetch_status="success",
            fetched_at=fetched_at,
        )
    except Exception as exc:  # noqa: BLE001 - preserve source fetch failures without crashing the pipeline.
        return PageFetchResult(
            url=url,
            page_title=None,
            page_excerpt=None,
            page_text_hash=None,
            page_cache_path=None,
            fetch_status="failed",
            fetched_at=fetched_at,
            failure_reason=str(exc),
        )
