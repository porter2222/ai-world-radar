# P1-3 HN 与 GitHub 采集接入新版链路计划 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 每个 task 必须先写测试、运行 RED、再写实现、运行 GREEN、更新文档并单独提交。

**Goal:** 把真实 HN / GitHub 公开来源稳定写入新版 `source_signals`，并让 P1-2 的 `scripts/run_event_pipeline.py` 能消费这些信号产出 `PublishedEvent`。

**Architecture:** P1-3 只补 source layer，不恢复旧 HN pipeline。HN / GitHub 采集器负责获取外部原始对象，source adapter 负责映射为 `SourceCreate` / `SourceSignalCreate`，`SignalService` 负责幂等入库，`run_event_pipeline.py` 负责从已入库信号继续进入 `SourceSignal -> EventCandidate -> EventDossier -> ReviewResult -> PublishedEvent`。

**Tech Stack:** Python 3.13, httpx 0.28.1, Pydantic 2.13.4, SQLAlchemy 2.0.41, LangGraph 1.2.4, pytest 8.4.0。

---

## 1. 当前阶段

P1-1 已完成新版后端数据底座，P1-2 已完成 LangGraph 最小闭环，并已物理删除旧 HN pipeline、旧 Agent stub、旧 `run_hn_pipeline.py` 和旧 legacy guard 测试。

当前唯一主链路是：

```text
SourceSignal
-> EventCandidate
-> EventDossier
-> ReviewResult
-> PublishedEvent
```

P1-3 的任务不是重新设计事件生产链路，而是把外部真实来源接入 `source_signals`。

## 2. 阶段边界

### 负责

- HN Algolia story 到 `SourceSignalCreate` 的稳定映射。
- GitHub releases 到 `SourceSignalCreate` 的稳定映射。
- `source_hash`、`source_item_id`、`canonical_url`、`heat_metrics`、`metadata` 的去重口径。
- 新增采集脚本，只负责采集并写入 `source_signals`。
- 更新 `run_event_pipeline.py`，允许从已入库的 source signals 选择信号运行。
- SQLite 临时库 smoke，证明先采集后生产可以首跑生成 `PublishedEvent`。
- 更新测试记录、项目状态、文档索引和 HTML 阅读版。

### 不负责

- 不恢复 `EvidenceCard / EventCluster / Brief / BriefItem` 旧链路。
- 不接真实 LLM Agent、prompt、repair prompt 或 tool-calling。
- 不做完整事实核验。
- 不开发 FastAPI、Next.js 前端、后台 UI、Redis、队列、对象存储或向量数据库。
- 不实现 GitHub Trending HTML 抓取；P1-3 先选择公开 REST API 更稳定的 releases。
- 不把采集脚本和发布 workflow 强耦合；两者用数据库中的 `source_signals` 衔接。

## 3. 文件结构

本阶段预计新增或修改：

```text
apps/worker/worker/sources/__init__.py
apps/worker/worker/sources/hn_source.py
apps/worker/worker/collectors/github_releases.py
apps/worker/worker/sources/github_source.py
apps/worker/scripts/collect_source_signals.py
apps/worker/scripts/run_event_pipeline.py
apps/worker/tests/fixtures/github_releases_response.json
apps/worker/tests/test_hn_source_signal_adapter.py
apps/worker/tests/test_github_releases_collector.py
apps/worker/tests/test_collect_source_signals_script.py
apps/worker/tests/test_run_event_pipeline_script.py
docs/07-验收与运行/后端P1测试记录.md
docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md
docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.html
docs/05-实现计划/README.md
docs/00-项目总览/项目状态.md
docs/00-项目总览/文档索引.md
docs/README.md
```

## 4. 数据映射口径

### 4.1 HN Algolia

`SourceCreate`：

```text
source_key=hn_algolia
name=Hacker News Algolia
source_type=community
fetch_method=api
entry_url=https://hn.algolia.com/api/v1/search_by_date
```

`SourceSignalCreate`：

```text
source_item_id=<HN objectID>
source_hash=hn_algolia:<HN objectID>
original_title=<HN title>
original_url=<hit url or https://news.ycombinator.com/item?id=<HN objectID>>
canonical_url=<normalize_url(original_url)>
published_at=<created_at>
raw_summary=<HN points/comments/query/story_text 摘要>
heat_metrics={"points": points, "comments": num_comments, "hn_heat_score": hn_heat_score}
metadata={"source": "hn_algolia", "author": author, "matched_query": matched_query, "hn_url": hn_url}
```

### 4.2 GitHub Releases

`SourceCreate`：

```text
source_key=github_releases
name=GitHub Releases
source_type=code_hosting
fetch_method=api
entry_url=https://api.github.com
```

`SourceSignalCreate`：

```text
source_item_id=<owner>/<repo>#<release id>
source_hash=github_releases:<owner>/<repo>:<release id>
original_title=<owner>/<repo> released <release name or tag>
original_url=<html_url>
canonical_url=<normalize_url(html_url)>
published_at=<published_at>
raw_summary=<release body 摘要>
heat_metrics={"assets_count": assets_count, "is_prerelease": bool, "is_draft": bool}
metadata={"source": "github_releases", "owner": owner, "repo": repo, "tag_name": tag_name}
```

## 5. 任务拆解

### Task 0: P1-3 计划与入口文档

**Files:**

- Create: `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md`
- Create: `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.html`
- Modify: `docs/README.md`
- Modify: `docs/05-实现计划/README.md`
- Modify: `docs/00-项目总览/项目状态.md`
- Modify: `docs/00-项目总览/文档索引.md`

- [x] **Step 1: Write plan and HTML reading version**

写入本计划和对应 HTML，让后续代理能只读文档理解阶段目标。

执行记录：已新增本计划 Markdown、HTML 阅读版，并同步更新 `docs/README.md`、`docs/05-实现计划/README.md`、`docs/00-项目总览/文档索引.md` 和 `docs/00-项目总览/项目状态.md`。

- [x] **Step 2: Run documentation checks**

Run:

```powershell
git diff --check
```

Expected:

```text
无输出，退出码为 0
```

执行记录：已运行 `git diff --check`，真实结果为退出码 0；PowerShell 输出仅包含既有工作区换行提示，没有 trailing whitespace 或冲突标记错误。

- [ ] **Step 3: Commit**

```powershell
git add docs/README.md docs/05-实现计划/README.md docs/05-实现计划/P1-3* docs/00-项目总览/项目状态.md docs/00-项目总览/文档索引.md
git commit -m "docs: add p1-3 source collection plan"
```

### Task 1: HN SourceSignal adapter

**Files:**

- Create: `apps/worker/worker/sources/__init__.py`
- Create: `apps/worker/worker/sources/hn_source.py`
- Create: `apps/worker/tests/test_hn_source_signal_adapter.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md`

- [x] **Step 1: Write failing test**

Test target:

```python
from worker.collectors.hn_algolia import HNStory
from worker.sources.hn_source import build_hn_source, hn_story_to_signal


def test_hn_story_maps_to_source_signal_create():
    story = HNStory(...)
    source = build_hn_source()
    signal = hn_story_to_signal(story)

    assert source.source_key == "hn_algolia"
    assert signal.source_hash == "hn_algolia:1001"
    assert signal.canonical_url == "https://example.com/openai-coding-agent"
    assert signal.heat_metrics["hn_heat_score"] == 65
```

执行记录：已新增 `apps/worker/tests/test_hn_source_signal_adapter.py`，覆盖 HN source 配置、HNStory 到 SourceSignalCreate 映射、无外链时回退到 HN item URL 三个场景。实际测试数比计划示例多 1 个，用于固定 HN item URL fallback 口径。

- [x] **Step 2: Run RED**

Run:

```powershell
cd "C:\Users\admin\.config\superpowers\worktrees\AI World Radar\p1-data-foundation\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_hn_source_signal_adapter.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.sources'
```

执行记录：首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_hn_source_signal_adapter.py -v`，真实结果为 `collected 0 items / 1 error`，失败原因为 `ModuleNotFoundError: No module named 'worker.sources'`，RED 成立。

- [x] **Step 3: Implement adapter**

`hn_source.py` must expose:

```python
def build_hn_source() -> SourceCreate: ...
def hn_story_to_signal(story: HNStory) -> SourceSignalCreate: ...
```

函数级中文 docstring 必须说明输入和输出。

执行记录：已新增 `apps/worker/worker/sources/__init__.py` 和 `apps/worker/worker/sources/hn_source.py`。`build_hn_source` 构造 HN Algolia SourceCreate；`hn_story_to_signal` 将 HNStory 映射为 SourceSignalCreate；辅助函数负责 HN item URL、canonical URL 和 raw_summary。新增函数均包含中文 docstring，说明输入与输出。

- [x] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hn_source_signal_adapter.py -v
```

Expected:

```text
3 passed
```

执行记录：重新运行 `.\.venv\Scripts\python.exe -m pytest tests/test_hn_source_signal_adapter.py -v`，真实结果为 `collected 3 items`，3 个测试均 `PASSED`，最终 `3 passed in 0.13s`。

- [x] **Step 5: Commit**

```powershell
git add apps/worker/worker/sources apps/worker/tests/test_hn_source_signal_adapter.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-3*
git commit -m "feat(worker): map hn stories to source signals"
```

执行记录：已提交 `feat(worker): map hn stories to source signals`。

### Task 2: GitHub releases collector and adapter

**Files:**

- Create: `apps/worker/worker/collectors/github_releases.py`
- Create: `apps/worker/worker/sources/github_source.py`
- Create: `apps/worker/tests/fixtures/github_releases_response.json`
- Create: `apps/worker/tests/test_github_releases_collector.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md`

- [x] **Step 1: Write failing tests**

Tests must cover:

- GitHub releases JSON maps to `GitHubRelease`.
- Release maps to `SourceSignalCreate`.
- `source_hash` is stable for the same owner/repo/release id.

执行记录：已新增 `apps/worker/tests/fixtures/github_releases_response.json` 和 `apps/worker/tests/test_github_releases_collector.py`。测试覆盖 GitHub release JSON 到 `GitHubRelease`、payload 按 `published_at` 倒序并限制数量、`GitHubRelease` 到 `SourceSignalCreate` 的映射。

- [x] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_github_releases_collector.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.collectors.github_releases'
```

执行记录：首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_github_releases_collector.py -v`，真实结果为 `collected 0 items / 1 error`，失败原因为 `ModuleNotFoundError: No module named 'worker.collectors.github_releases'`，RED 成立。

- [x] **Step 3: Implement collector and adapter**

Collector must expose:

```python
@dataclass(frozen=True)
class GitHubRelease: ...
def parse_github_release(payload: dict, owner: str, repo: str) -> GitHubRelease: ...
def collect_from_github_releases_payload(payload: list[dict], owner: str, repo: str, limit: int) -> list[GitHubRelease]: ...
def fetch_github_releases(owner: str, repo: str, limit: int = 10, token: str | None = None) -> list[GitHubRelease]: ...
```

Adapter must expose:

```python
def build_github_releases_source() -> SourceCreate: ...
def github_release_to_signal(release: GitHubRelease) -> SourceSignalCreate: ...
```

函数级中文 docstring 必须说明输入和输出。

执行记录：已新增 `apps/worker/worker/collectors/github_releases.py` 和 `apps/worker/worker/sources/github_source.py`，并更新 `worker/sources/__init__.py` 导出 GitHub source adapter。新增函数和 `GitHubRelease` 均包含中文 docstring，说明输入与输出。

- [x] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_github_releases_collector.py -v
```

Expected:

```text
3 passed
```

执行记录：重新运行 `.\.venv\Scripts\python.exe -m pytest tests/test_github_releases_collector.py -v`，真实结果为 `collected 3 items`，3 个测试均 `PASSED`，最终 `3 passed in 0.39s`。随后运行 `.\.venv\Scripts\python.exe -m pytest tests/test_hn_source_signal_adapter.py tests/test_github_releases_collector.py -v`，真实结果为 `6 passed in 0.21s`，确认新增导出未破坏 Task 1。

- [x] **Step 5: Commit**

```powershell
git add apps/worker/worker/collectors/github_releases.py apps/worker/worker/sources/github_source.py apps/worker/tests/fixtures/github_releases_response.json apps/worker/tests/test_github_releases_collector.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-3*
git commit -m "feat(worker): collect github releases as source signals"
```

执行记录：已提交 `feat(worker): collect github releases as source signals`。

### Task 3: Collection script writes SourceSignal only

**Files:**

- Create: `apps/worker/scripts/collect_source_signals.py`
- Create: `apps/worker/tests/test_collect_source_signals_script.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md`

- [ ] **Step 1: Write failing script test**

Test must prove:

- Script can create schema for smoke.
- Script can collect fixture-injected HN and GitHub signals without running workflow.
- SQLite DB contains `source_signals` rows after script exits.

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py -v
```

Expected:

```text
can't open file 'scripts/collect_source_signals.py'
```

- [ ] **Step 3: Implement script**

Script behavior:

```text
--database-url <url>
--create-schema-for-smoke
--source hn
--source github
--hn-days 7
--hn-limit 5
--github-repo owner/repo
--github-limit 3
--github-token-env GITHUB_TOKEN
```

Output JSON:

```json
{
  "status": "succeeded",
  "sources_count": 2,
  "signals_count": 4,
  "source_keys": ["github_releases", "hn_algolia"]
}
```

The script must not call `run_event_pipeline`.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/scripts/collect_source_signals.py apps/worker/tests/test_collect_source_signals_script.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-3*
git commit -m "feat(worker): add source signal collection script"
```

### Task 4: Event pipeline consumes collected signals

**Files:**

- Modify: `apps/worker/scripts/run_event_pipeline.py`
- Modify: `apps/worker/tests/test_run_event_pipeline_script.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md`

- [ ] **Step 1: Write failing script test**

Add test proving:

- Pre-seed a real `SourceSignal` via `SignalService`.
- Run script with `--source-key hn_algolia --limit 1`.
- Script returns `published_count=1`.

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_run_event_pipeline_script.py -v
```

Expected:

```text
argparse rejects --source-key
```

- [ ] **Step 3: Implement source selection**

`run_event_pipeline.py` must add:

```text
--source-key <source_key>
--limit <N>
```

Selection rule:

```text
select SourceSignal joined with Source by source_key, sorted by created_at desc, limited by N
```

If no signals exist, return JSON failure explaining no signal ids are available.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_run_event_pipeline_script.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/scripts/run_event_pipeline.py apps/worker/tests/test_run_event_pipeline_script.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-3*
git commit -m "feat(worker): run event pipeline from collected signals"
```

### Task 5: P1-3 smoke, docs, and phase handoff

**Files:**

- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md`
- Modify: `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.html`
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

- [ ] **Step 2: Run fresh SQLite smoke**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/collect_source_signals.py --database-url "sqlite+pysqlite:///scratch/p1_3_smoke.sqlite" --create-schema-for-smoke --source hn --hn-limit 1 --source github --github-repo openai/openai-python --github-limit 1
.\.venv\Scripts\python.exe scripts/run_event_pipeline.py --database-url "sqlite+pysqlite:///scratch/p1_3_smoke.sqlite" --source-key hn_algolia --limit 1 --run-key "manual-p1-3-smoke"
```

Expected:

```text
collect_source_signals.py 输出 status=succeeded 且 signals_count >= 1
run_event_pipeline.py 输出 status=succeeded 且 published_count=1
```

If live network or GitHub rate limit fails, run a fixture-mode smoke and record the live failure text exactly in `后端P1测试记录.md`。

- [ ] **Step 3: Update docs with real outputs**

`docs/07-验收与运行/后端P1测试记录.md` must state:

- 测试了什么。
- 使用了什么测试数据。
- 执行了什么命令。
- 命令真实输出摘要是什么。
- 失败过哪些测试，以及如何修复。
- 哪些范围没有覆盖。
- 当前是否可以进入 P1-4。

- [ ] **Step 4: Run documentation check**

Run:

```powershell
git diff --check
rg "待[补]充|占[位]|预[计]通过|应[该]通过" docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md
```

Expected:

```text
git diff --check 无输出
rg 无匹配
```

- [ ] **Step 5: Commit**

```powershell
git add docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-3* docs/05-实现计划/README.md docs/00-项目总览/项目状态.md docs/00-项目总览/文档索引.md docs/README.md
git commit -m "docs: record p1-3 source collection acceptance"
```

## 6. 验收标准

P1-3 完成后必须满足：

- HN Algolia story 可以映射为新版 `SourceSignalCreate`。
- GitHub release 可以映射为新版 `SourceSignalCreate`。
- `source_hash` 对同一外部对象稳定，且通过 `SignalService` 幂等写入。
- `collect_source_signals.py` 可以只采集并写入 `source_signals`，不运行事件生产 workflow。
- `run_event_pipeline.py` 可以用已入库 source signals 运行，不依赖 `--seed-demo-signal`。
- worker 全量 pytest 通过。
- 全新 SQLite smoke 证明“采集 -> 入库信号 -> 事件生产 -> 发布快照”首跑可用。
- 文档记录真实命令、真实输出、测试数据、失败修复、未覆盖范围和是否可以进入 P1-4。

## 7. 风险与处理方式

- HN / GitHub live API 可能网络失败或限流：测试用 fixture 和 fake transport 保证回归稳定，live smoke 失败时记录真实失败文本并补 fixture-mode smoke。
- GitHub releases 不是 GitHub Trending：P1-3 选择官方 REST API 保证稳定，Trending HTML 解析后置。
- HN 是热议源，不等同事实源：P1-3 只写 source signal，不在采集层做真实性判断。
- SQLite 与 PostgreSQL 方言差异：P1-3 smoke 先使用 SQLite；PostgreSQL migration smoke 仍列为未覆盖范围，后续部署准备阶段补。

## 8. 执行交接

本计划保存于 `docs/05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md`。当前建议按 Task 0 到 Task 5 顺序执行，每个 task 单独 RED/GREEN、更新文档并提交。
