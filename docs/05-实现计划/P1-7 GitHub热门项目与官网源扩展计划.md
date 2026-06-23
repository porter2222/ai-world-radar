# P1-7 GitHub 热门项目与官网源扩展计划 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不引入账号池、强反爬、社交平台大爬虫或新数据库表的前提下，补齐 GitHub 热门项目发现源和官网/RSS 官方源，让更多公开信号稳定进入 `source_signals`。

**Architecture:** 本阶段继续沿用新版主链路 `SourceSignal -> EventCandidate -> EventDossier -> ReviewResult -> PublishedEvent`。新增 source layer 只负责采集和映射，不直接调用 Agent、不直接发布、不改产品接口；`collect_source_signals.py` 负责把新源写入 `sources` / `source_signals`，后续仍由 `run_event_pipeline.py --source-key ...` 消费。

**Tech Stack:** Python 3.13, httpx 0.28.1, BeautifulSoup 4.13.4, Pydantic 2.13.4, SQLAlchemy 2.0.41, pytest 8.4.0, PostgreSQL / SQLite smoke。

---

## 1. 当前阶段

P1-3 已接入 `hn_algolia` 和 `github_releases`。2026-06-23 已完成 HN 与 GitHub Releases 的真实链路验收，但用户已明确修正 GitHub source 方向：单仓库 release 不能代表“GitHub 上正在变热的 AI 项目”。因此本阶段把 GitHub 主 source 从“已知仓库发版监控”升级为“GitHub repo momentum / GitHub 热门项目发现”。

本阶段不做 arXiv / 论文源。原因：论文源信息密度高、解释成本高，容易把 P1 产品带偏成论文雷达；等产品页面与事件详情稳定后再作为 P1.5/P2 增强。

## 2. 阶段边界

### 负责

- 新增 `github_repo_trends` source：
  - 通过 GitHub Search API 搜索 AI 相关仓库。
  - 记录总 stars、forks、语言、topics、最近 push 时间。
  - 在 `source_signals` 内保留 repo 快照。
  - 从第二次采集开始计算 `stars_delta_since_last` 和 `stars_delta_rate`。
- 新增 `official_feeds` / `official_news` source：
  - 优先解析 RSS / Atom。
  - 对无 RSS 的官网，只允许轻量 HTML 列表页解析，不做深层爬取。
  - 初始目标源包括 NVIDIA RSS、GitHub Changelog、OpenAI News、Anthropic News、Google DeepMind Blog。
- 扩展 `collect_source_signals.py`：
  - 支持 `--source github_trends`。
  - 支持 `--source official_feeds`。
  - 保留 fixture mode，确保回归测试不依赖外网。
- 更新验收记录、项目状态、文档索引、实现计划 README。

### 不负责

- 不接 X / Reddit / YouTube。
- 不做账号池、代理池、验证码绕过、浏览器自动化反爬。
- 不做 GitHub Trending HTML 页面解析；先用官方 Search API 和本地快照计算趋势。
- 不新增数据库表；趋势快照先复用 `source_signals`。
- 不做 arXiv / papers / 论文总结。
- 不让 Agent 直接写库或直接发布。
- 不改变默认 `AGENT_MODE=stub`；真实 LLM 仍需显式开启。

## 3. 数据口径

### 3.1 GitHub repo momentum

`SourceCreate`：

```text
source_key=github_repo_trends
name=GitHub Repo Trends
source_type=code_hosting
fetch_method=api
entry_url=https://api.github.com/search/repositories
```

`SourceSignalCreate`：

```text
source_item_id=<owner>/<repo>
source_hash=github_repo_trends:<owner>/<repo>:<snapshot_bucket>
original_title=<owner>/<repo> is gaining attention on GitHub
original_url=<html_url>
canonical_url=<normalize_url(html_url)>
published_at=<pushed_at or updated_at>
raw_summary=<description + stars/forks/language/topics 摘要>
heat_metrics={
  "stargazers_count": int,
  "forks_count": int,
  "open_issues_count": int,
  "stars_delta_since_last": int | null,
  "previous_stargazers_count": int | null,
  "stars_delta_rate": float | null,
  "is_archived": bool,
  "is_fork": bool
}
metadata={
  "source": "github_repo_trends",
  "repo_id": str,
  "full_name": str,
  "owner": str,
  "repo": str,
  "language": str | null,
  "topics": list[str],
  "query": str,
  "snapshot_bucket": str,
  "pushed_at": str | null,
  "created_at": str | null,
  "updated_at": str | null
}
```

快照规则：

- `snapshot_bucket` 默认按 UTC 小时生成，例如 `2026062311`。
- 同一 repo 同一 bucket 幂等 upsert。
- 计算增量时，脚本按 `source_key=github_repo_trends` 和 `source_item_id=<owner>/<repo>` 查询上一条不同 bucket 的 signal。
- 首次采集无历史时，`stars_delta_since_last=null`，但仍保留 `stargazers_count` 作为冷启动热度。

### 3.2 官方 RSS / 官网新闻源

`SourceCreate`：

```text
source_key=<profile source_key>
name=<profile name>
source_type=official
fetch_method=rss|atom|html
entry_url=<feed_or_page_url>
```

`SourceSignalCreate`：

```text
source_item_id=<entry id or canonical URL>
source_hash=official_news:<source_key>:<entry id/hash>
original_title=<entry title>
original_url=<entry url>
canonical_url=<normalize_url(entry url)>
published_at=<published/updated date if present>
raw_summary=<entry summary/excerpt>
heat_metrics={"official_source": true}
metadata={
  "source": "official_news",
  "profile_key": <source_key>,
  "profile_name": <name>,
  "mode": "rss" | "atom" | "html"
}
```

## 4. 文件结构

预计新增或修改：

```text
apps/worker/worker/collectors/github_repo_trends.py
apps/worker/worker/sources/github_trends_source.py
apps/worker/worker/collectors/official_news.py
apps/worker/worker/sources/official_news_source.py
apps/worker/worker/sources/__init__.py
apps/worker/scripts/collect_source_signals.py
apps/worker/tests/fixtures/github_repo_search_response.json
apps/worker/tests/fixtures/official_rss_feed.xml
apps/worker/tests/fixtures/official_atom_feed.xml
apps/worker/tests/fixtures/official_news_page.html
apps/worker/tests/test_github_repo_trends_collector.py
apps/worker/tests/test_official_news_collector.py
apps/worker/tests/test_collect_source_signals_script.py
docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.md
docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.html
docs/05-实现计划/README.md
docs/00-项目总览/项目状态.md
docs/00-项目总览/文档索引.md
docs/README.md
docs/07-验收与运行/后端P1测试记录.md
```

## 5. 任务拆解

### Task 0: P1-7 plan, baseline, and docs entry

**Files:**

- Create: `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.md`
- Create: `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.html`
- Modify: `docs/README.md`
- Modify: `docs/05-实现计划/README.md`
- Modify: `docs/00-项目总览/项目状态.md`
- Modify: `docs/00-项目总览/文档索引.md`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`

- [x] **Step 1: Run baseline**

Run:

```powershell
cd "C:\Users\admin\.config\superpowers\worktrees\AI World Radar\p1-data-foundation\apps\worker"
.\.venv\Scripts\python.exe -m pytest -v
```

Expected:

```text
96 passed
```

- [x] **Step 2: Write this plan and HTML reading version**

The plan must state:

- GitHub Releases is no longer the primary GitHub discovery source.
- `github_repo_trends` is the new GitHub discovery source.
- Official sources use RSS/Atom first, light HTML page parsing second.
- arXiv and papers are out of scope.

- [x] **Step 3: Run documentation check**

Run:

```powershell
git diff --check
rg "待[补]充|占[位]|预[计]通过|应[该]通过" docs/05-实现计划/P1-7*
```

Expected:

```text
git diff --check exits 0
rg exits 1 with no matches
```

- [x] **Step 4: Commit**

```powershell
git add docs/README.md docs/05-实现计划/README.md docs/05-实现计划/P1-7* docs/00-项目总览/项目状态.md docs/00-项目总览/文档索引.md docs/07-验收与运行/后端P1测试记录.md
git commit -m "docs(worker): add P1-7 source expansion plan"
```

### Task 1: GitHub repo trends collector and source adapter

**Files:**

- Create: `apps/worker/worker/collectors/github_repo_trends.py`
- Create: `apps/worker/worker/sources/github_trends_source.py`
- Create: `apps/worker/tests/fixtures/github_repo_search_response.json`
- Create: `apps/worker/tests/test_github_repo_trends_collector.py`
- Modify: `apps/worker/worker/sources/__init__.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.md`

- [x] **Step 1: Write failing tests**

Test target:

```python
from worker.collectors.github_repo_trends import collect_from_github_search_payload, parse_github_repository
from worker.sources.github_trends_source import build_github_repo_trends_source, github_repo_trend_to_signal


def test_github_search_repo_maps_to_trend_signal():
    repo = parse_github_repository(load_payload()["items"][0], query="topic:llm stars:>100")
    source = build_github_repo_trends_source()
    signal = github_repo_trend_to_signal(
        repo,
        snapshot_bucket="2026062311",
        previous_stargazers_count=1000,
    )

    assert source.source_key == "github_repo_trends"
    assert signal.source_key == "github_repo_trends"
    assert signal.source_item_id == "example/fast-llm"
    assert signal.source_hash == "github_repo_trends:example/fast-llm:2026062311"
    assert signal.heat_metrics["stargazers_count"] == 1250
    assert signal.heat_metrics["stars_delta_since_last"] == 250
    assert signal.metadata["query"] == "topic:llm stars:>100"
```

- [x] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_github_repo_trends_collector.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.collectors.github_repo_trends'
```

- [x] **Step 3: Implement collector and adapter**

`github_repo_trends.py` must expose:

```python
@dataclass(frozen=True)
class GitHubRepositoryTrend: ...

def parse_github_repository(payload: dict[str, Any], query: str) -> GitHubRepositoryTrend: ...

def collect_from_github_search_payload(
    payload: dict[str, Any],
    query: str,
    limit: int,
    min_stars: int,
) -> list[GitHubRepositoryTrend]: ...

def fetch_github_repository_trends(
    query: str,
    limit: int = 10,
    min_stars: int = 100,
    token: str | None = None,
) -> list[GitHubRepositoryTrend]: ...
```

`github_trends_source.py` must expose:

```python
def build_github_repo_trends_source() -> SourceCreate: ...

def github_repo_trend_to_signal(
    repo: GitHubRepositoryTrend,
    *,
    snapshot_bucket: str,
    previous_stargazers_count: int | None = None,
) -> SourceSignalCreate: ...
```

Every new function must have Chinese docstrings describing input and output.

- [x] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_github_repo_trends_collector.py -v
```

Expected:

```text
3 passed
```

Actual:

```text
4 passed
```

执行偏差：原计划只要求 3 个测试；实际额外补了“首次采集无历史快照时 star delta 为 null”的边界测试，因此 GREEN 结果为 4 passed。

- [x] **Step 5: Commit**

```powershell
git add apps/worker/worker/collectors/github_repo_trends.py apps/worker/worker/sources/github_trends_source.py apps/worker/worker/sources/__init__.py apps/worker/tests/fixtures/github_repo_search_response.json apps/worker/tests/test_github_repo_trends_collector.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-7*
git commit -m "feat(worker): collect github repo trends as source signals"
```

### Task 2: Collection script supports GitHub repo trends

**Files:**

- Modify: `apps/worker/scripts/collect_source_signals.py`
- Modify: `apps/worker/tests/test_collect_source_signals_script.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.md`

- [x] **Step 1: Write failing script tests**

Add tests proving:

- `--source github_trends` is accepted.
- Fixture mode writes `github_repo_trends` source and signal.
- A previous repo snapshot produces `stars_delta_since_last`.
- Script still does not create `pipeline_runs` or `published_events`.

Example assertion:

```python
assert summary["source_keys"] == ["github_repo_trends"]
assert signal.heat_metrics["stars_delta_since_last"] == 250
assert counts["pipeline_runs"] == 0
assert counts["published_events"] == 0
```

- [x] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py -v
```

Expected:

```text
argument --source: invalid choice: 'github_trends'
```

- [x] **Step 3: Implement script integration**

Add CLI options:

```text
--source github_trends
--github-trend-query <query>    repeatable
--github-trend-limit <N>
--github-trend-min-stars <N>
--github-trend-token-env GITHUB_TOKEN
--snapshot-bucket <YYYYMMDDHH>  test/smoke deterministic override
```

Add functions:

```python
def collect_github_repo_trend_signals(...): ...
def load_fixture_github_repo_trends(...): ...
def find_previous_stargazers_count(...): ...
```

- [x] **Step 4: Run GREEN and source regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py tests/test_github_repo_trends_collector.py tests/test_github_releases_collector.py tests/test_hn_source_signal_adapter.py -v
```

Expected:

```text
all selected tests passed
```

- [x] **Step 5: Commit**

```powershell
git add apps/worker/scripts/collect_source_signals.py apps/worker/tests/test_collect_source_signals_script.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-7*
git commit -m "feat(worker): collect github repo trend signals"
```

### Task 3: Official RSS / Atom / light HTML collector and adapter

**Files:**

- Create: `apps/worker/worker/collectors/official_news.py`
- Create: `apps/worker/worker/sources/official_news_source.py`
- Create: `apps/worker/tests/fixtures/official_rss_feed.xml`
- Create: `apps/worker/tests/fixtures/official_atom_feed.xml`
- Create: `apps/worker/tests/fixtures/official_news_page.html`
- Create: `apps/worker/tests/test_official_news_collector.py`
- Modify: `apps/worker/worker/sources/__init__.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.md`

- [ ] **Step 1: Write failing tests**

Test target:

```python
from worker.collectors.official_news import collect_from_feed_xml, collect_from_news_html, OfficialSourceProfile
from worker.sources.official_news_source import build_official_news_source, official_news_entry_to_signal


def test_rss_feed_entry_maps_to_source_signal():
    profile = OfficialSourceProfile(
        source_key="nvidia_news",
        name="NVIDIA News",
        mode="rss",
        entry_url="https://nvidianews.nvidia.com/rss",
    )
    entry = collect_from_feed_xml(load_xml("official_rss_feed.xml"), profile=profile, limit=1)[0]
    source = build_official_news_source(profile)
    signal = official_news_entry_to_signal(entry)

    assert source.source_key == "nvidia_news"
    assert signal.source_hash.startswith("official_news:nvidia_news:")
    assert signal.heat_metrics["official_source"] is True
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_official_news_collector.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.collectors.official_news'
```

- [ ] **Step 3: Implement collector and adapter**

`official_news.py` must expose:

```python
@dataclass(frozen=True)
class OfficialSourceProfile: ...

@dataclass(frozen=True)
class OfficialNewsEntry: ...

def collect_from_feed_xml(xml: str, *, profile: OfficialSourceProfile, limit: int) -> list[OfficialNewsEntry]: ...

def collect_from_news_html(html: str, *, profile: OfficialSourceProfile, limit: int) -> list[OfficialNewsEntry]: ...

def fetch_official_news(profile: OfficialSourceProfile, limit: int = 5) -> list[OfficialNewsEntry]: ...
```

`official_news_source.py` must expose:

```python
def build_official_news_source(profile: OfficialSourceProfile) -> SourceCreate: ...
def official_news_entry_to_signal(entry: OfficialNewsEntry) -> SourceSignalCreate: ...
```

HTML parsing boundary:

- Only parse the provided list page.
- Only extract title, URL, date, summary/excerpt.
- Do not follow every article page.
- Do not run a browser.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_official_news_collector.py -v
```

Expected:

```text
all tests passed
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/worker/collectors/official_news.py apps/worker/worker/sources/official_news_source.py apps/worker/worker/sources/__init__.py apps/worker/tests/fixtures/official_rss_feed.xml apps/worker/tests/fixtures/official_atom_feed.xml apps/worker/tests/fixtures/official_news_page.html apps/worker/tests/test_official_news_collector.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-7*
git commit -m "feat(worker): collect official news source signals"
```

### Task 4: Collection script supports official feeds

**Files:**

- Modify: `apps/worker/scripts/collect_source_signals.py`
- Modify: `apps/worker/tests/test_collect_source_signals_script.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.md`

- [ ] **Step 1: Write failing script tests**

Add tests proving:

- `--source official_feeds` is accepted.
- `--official-profile nvidia_news` writes source and signal in fixture mode.
- The script can combine `github_trends` and `official_feeds` without running workflow.

Example assertion:

```python
assert summary["source_keys"] == ["github_repo_trends", "nvidia_news"]
assert counts["source_signals"] == 2
assert counts["pipeline_runs"] == 0
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py -v
```

Expected:

```text
argument --source: invalid choice: 'official_feeds'
```

- [ ] **Step 3: Implement script integration**

Add CLI options:

```text
--source official_feeds
--official-profile <profile_key> repeatable
--official-limit <N>
```

Initial built-in profiles:

```text
nvidia_news      mode=rss   entry_url=https://nvidianews.nvidia.com/rss
github_changelog mode=html  entry_url=https://github.blog/changelog/
openai_news      mode=html  entry_url=https://openai.com/news/
anthropic_news   mode=html  entry_url=https://www.anthropic.com/news
deepmind_blog    mode=html  entry_url=https://deepmind.google/discover/blog/
```

If a live profile returns no entries because the page structure changed, the script should fail that profile with a clear error in stdout JSON rather than silently reporting success.

- [ ] **Step 4: Run GREEN and source regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py tests/test_official_news_collector.py tests/test_github_repo_trends_collector.py -v
```

Expected:

```text
all selected tests passed
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/scripts/collect_source_signals.py apps/worker/tests/test_collect_source_signals_script.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-7*
git commit -m "feat(worker): collect official feed signals"
```

### Task 5: P1-7 smoke, docs, and handoff

**Files:**

- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.md`
- Modify: `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.html`
- Modify: `docs/05-实现计划/README.md`
- Modify: `docs/00-项目总览/项目状态.md`
- Modify: `docs/00-项目总览/文档索引.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Run full worker pytest**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected:

```text
all tests passed
```

- [ ] **Step 2: Run fresh SQLite fixture smoke**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/collect_source_signals.py --database-url "sqlite+pysqlite:///scratch/p1_7_smoke.sqlite" --create-schema-for-smoke --fixture-mode --source github_trends --github-trend-query "topic:llm stars:>100" --github-trend-limit 1 --snapshot-bucket "2026062311" --source official_feeds --official-profile nvidia_news --official-limit 1
.\.venv\Scripts\python.exe scripts/run_event_pipeline.py --database-url "sqlite+pysqlite:///scratch/p1_7_smoke.sqlite" --source-key github_repo_trends --limit 1 --run-key "manual-p1-7-smoke"
```

Expected:

```text
collect_source_signals.py outputs status=succeeded and source_keys include github_repo_trends and nvidia_news
run_event_pipeline.py outputs status=succeeded and published_count=1
```

- [ ] **Step 3: Run live source smoke**

Run one live collection without real LLM:

```powershell
.\.venv\Scripts\python.exe scripts/collect_source_signals.py --database-url postgresql+psycopg://postgres:<password>@localhost:5432/ai_world_radar --source github_trends --github-trend-query "topic:llm stars:>100" --github-trend-limit 1 --source official_feeds --official-profile nvidia_news --official-limit 1
```

Expected:

```text
status=succeeded
source_keys include github_repo_trends and nvidia_news
PostgreSQL source_signals row count increases or same-bucket upsert is verified
```

This task does not require real LLM by default. If real LLM is run, it must be explicit with `--agent-mode llm` and recorded separately.

- [ ] **Step 4: Update docs with real outputs**

`docs/07-验收与运行/后端P1测试记录.md` must state:

- 测试了什么。
- 使用了什么 fixture 和 live 数据。
- 执行了什么命令。
- 命令真实输出摘要是什么。
- 失败过哪些测试，以及如何修复。
- 哪些范围没有覆盖。
- 是否可以进入下一阶段或前端联调。

- [ ] **Step 5: Run final checks**

Run:

```powershell
git diff --check
rg -n "postgres:c[j]y|sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY=sk|DEEPSEEK_API_KEY=sk|GITHUB_TOKEN=gh[pousr]_" docs apps/worker/tests apps/worker/scripts apps/worker/worker apps/worker/pyproject.toml
```

Expected:

```text
git diff --check exits 0
secret scan has no matches
```

- [ ] **Step 6: Commit and push**

```powershell
git add docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-7* docs/05-实现计划/README.md docs/00-项目总览/项目状态.md docs/00-项目总览/文档索引.md docs/README.md
git commit -m "docs(worker): record P1-7 source expansion acceptance"
git push origin codex/p1-data-foundation
```

## 6. 验收标准

P1-7 完成后必须满足：

- `github_repo_trends` 可以从 GitHub Search API payload 映射为 `SourceSignalCreate`。
- GitHub repo trend 快照支持冷启动星数记录和二次采集 star delta。
- `official_news` 可以解析 RSS、Atom 和轻量 HTML 列表页。
- `collect_source_signals.py` 支持 `github_trends` 和 `official_feeds`，且仍只写 `sources` / `source_signals`。
- 采集脚本不创建 `pipeline_runs`、`event_candidates`、`event_dossiers`、`review_results` 或 `published_events`。
- 全量 worker pytest 通过。
- fresh SQLite smoke 证明新源采集后能被现有 `run_event_pipeline.py --source-key` 消费。
- live PostgreSQL source smoke 证明至少一个 GitHub trend 和一个官方源可以真实入库。
- 文档记录真实命令、真实输出、失败修复、未覆盖范围和下一阶段建议。

## 7. 风险与处理方式

- GitHub Search API 有限流：默认使用少量 query profile 和小 limit；可选 `GITHUB_TOKEN`，但不要求账号池。
- GitHub Search 不能直接返回“近日 star 增长”：系统用本地 `source_signals` 快照计算 delta，首跑只记录冷启动星数。
- 官网 HTML 结构可能变化：HTML collector 只做列表页轻量解析；live smoke 如果抓不到条目，要在测试记录中写明真实失败，不假装通过。
- RSS/Atom 字段差异：collector 同时支持 RSS item 和 Atom entry，并对缺失 date/summary 做明确兜底。
- 噪声和重复：本阶段只进入 `source_signals`，事件合并和发布仍由后续 pipeline/Agent 控制。

## 8. 执行交接

本计划保存于 `docs/05-实现计划/P1-7 GitHub热门项目与官网源扩展计划.md`。执行时必须按 Task 0 到 Task 5 顺序推进；每个代码 task 必须先写测试、运行 RED、再写实现、运行 GREEN、更新文档并单独 commit。默认不运行真实 LLM，除非用户明确要求或验收任务显式打开 `--agent-mode llm`。
