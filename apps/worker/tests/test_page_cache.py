from pathlib import Path

from worker.collectors.page_cache import build_page_cache_path, extract_readable_text, write_cached_page


FIXTURE = Path(__file__).parent / "fixtures" / "sample_page.html"


def test_extract_readable_text_removes_script_and_style_noise():
    """验证 HTML 正文抽取会去掉脚本和样式噪声。

    输入：sample_page.html fixture。
    输出：断言正文包含有效文本且不包含 script/style 内容。
    """
    html = FIXTURE.read_text(encoding="utf-8")

    result = extract_readable_text(html)

    assert result.title == "Sample AI launch page"
    assert "OpenAI announced a new coding agent" in result.text
    assert "window.__noise" not in result.text
    assert "body { color" not in result.text


def test_build_page_cache_path_uses_date_and_hn_id():
    """验证原文缓存路径格式。

    输入：runtime 目录、HN ID 和固定日期。
    输出：断言生成路径符合 `runtime/source-pages/date/hn-id-page.txt`。
    """
    path = build_page_cache_path(runtime_dir=Path("runtime"), hn_id="123456", fetched_date="2026-06-09")

    assert path == Path("runtime") / "source-pages" / "2026-06-09" / "hn-123456-page.txt"


def test_write_cached_page_writes_text_and_hash(tmp_path):
    """验证缓存写入会落文件并生成 hash。

    输入：临时路径和正文文本。
    输出：断言文件内容和 hash 都存在。
    """
    cache_path = tmp_path / "source-pages" / "2026-06-09" / "hn-123456-page.txt"

    result = write_cached_page(cache_path, "A cached AI page")

    assert cache_path.read_text(encoding="utf-8") == "A cached AI page"
    assert result.cache_path == cache_path
    assert result.text_hash
