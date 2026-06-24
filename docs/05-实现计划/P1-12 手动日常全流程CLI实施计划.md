# P1-12 手动日常全流程 CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增无需命令行参数的一键日常 pipeline CLI，让用户可直接运行 `scripts/run_daily_pipeline.py` 完成“采集 -> 本轮新增信号 -> LLM selector -> 发布”。

**Architecture:** 把核心编排放入 `DailyPipelineService`，CLI 只负责读取 `.env`、创建 session、调用 service 和输出 JSON。service 复用现有 `collect_source_signals.py`、`EditorialCandidateService`、`select_candidate_groups()` 和 `run_event_pipeline()`，默认只处理本轮新增信号。

**Tech Stack:** Python 3.13、SQLAlchemy、Pydantic、pytest、现有 Worker service / script 模块。

---

## Files

- Create: `apps/worker/worker/services/daily_pipeline_service.py`
- Create: `apps/worker/scripts/run_daily_pipeline.py`
- Create: `apps/worker/tests/test_daily_pipeline_service.py`
- Create: `apps/worker/tests/test_run_daily_pipeline_script.py`
- Modify: `.env.example`
- Modify: `apps/worker/tests/test_config.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/00-项目总览/项目状态.md`

## Task 1: 配置键补齐

**Files:**
- Modify: `.env.example`
- Modify: `apps/worker/tests/test_config.py`

- [x] **Step 1: Write failing test**

已新增测试：

```python
def test_env_example_contains_local_runtime_closure_keys():
    env_example = load_settings().project_root / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    required_keys = {
        "DATABASE_URL",
        "AGENT_MODE",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_USER_AGENT",
        "GITHUB_TOKEN",
        "DAILY_PIPELINE_SOURCE_GROUP",
        "DAILY_PIPELINE_LOOKBACK_HOURS",
        "DAILY_PIPELINE_SELECTOR_BATCH_SIZE",
        "DAILY_PIPELINE_MAX_SELECTED",
        "DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR",
        "DAILY_PIPELINE_DISABLE_AGENT_FALLBACK",
        "AI_WORLD_RADAR_API_BASE_URL",
    }
    present_keys = {
        line.split("=", maxsplit=1)[0].strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    assert required_keys <= present_keys
    assert "sk-" not in content
    assert "cjy2037388336" not in content
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
cd apps/worker
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -v
```

Actual:

```text
1 failed, 1 passed in 0.37s
```

Failure reason: `.env.example` 缺少 `GITHUB_TOKEN` 和 `DAILY_PIPELINE_*` 键。

- [x] **Step 3: Write minimal implementation**

已补 `.env.example`：

```env
GITHUB_TOKEN=
DAILY_PIPELINE_SOURCE_GROUP=daily_all
DAILY_PIPELINE_LOOKBACK_HOURS=8
DAILY_PIPELINE_SELECTOR_BATCH_SIZE=30
DAILY_PIPELINE_MAX_SELECTED=5
DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR=true
DAILY_PIPELINE_DISABLE_AGENT_FALLBACK=true
```

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_smoke_env_connectivity_script.py -v
```

Actual:

```text
5 passed, 1 skipped in 9.87s
```

## Task 2: DailyPipelineService 编排

**Files:**
- Create: `apps/worker/worker/services/daily_pipeline_service.py`
- Test: `apps/worker/tests/test_daily_pipeline_service.py`

- [x] **Step 1: Write failing tests**

已新增测试：

```python
def test_daily_pipeline_service_processes_only_signals_collected_after_run_start(...):
    """验证只处理本轮新增信号。"""

def test_daily_pipeline_service_returns_no_new_signals_without_running_selector(...):
    """验证本轮无新增信号时不调用 selector 和 pipeline。"""

def test_daily_pipeline_service_applies_max_selected_limit(...):
    """验证 max_selected 能限制真实 pipeline run 数量。"""

def test_daily_pipeline_service_reports_selector_rejected_and_manual_review_counts(...):
    """验证 summary 保留 selector rejected / manual_review 计数。"""
```

Use SQLite in-memory / temp DB, fake collector callable, fake selector agent, and stub `pipeline_runner` function. Do not call real network or LLM.

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_daily_pipeline_service.py -v
```

Actual:

```text
ModuleNotFoundError: No module named 'worker.services.daily_pipeline_service'
```

- [x] **Step 3: Implement service**

已创建 `DailyPipelineService`，并为公开函数保留中文 docstring：

```python
@dataclass(frozen=True)
class DailyPipelineConfig:
    source_group: str = "daily_all"
    lookback_hours: int = 8
    selector_batch_size: int = 30
    continue_on_source_error: bool = True
    disable_agent_fallback: bool = True
    max_selected: int | None = 5
    agent_mode: str = "llm"


class DailyPipelineService:
    def run_once(self, config: DailyPipelineConfig) -> dict[str, object]:
        ...
```

Key behavior:

- Capture `collection_started_at = datetime.now(UTC)` before collecting.
- Build argparse Namespace compatible with `collect_selected_sources()`.
- Run collection and commit/flush within same session.
- Query `SourceSignal.collected_at >= collection_started_at` and `pipeline_run_id is None`.
- Monkeypatch-free production path: add helper that builds candidate groups from explicit signal rows instead of relying on private `_load_signals`.
- Call `select_candidate_groups(groups, top_n=len(groups), agent_mode=config.agent_mode, allow_fallback=not config.disable_agent_fallback, batch_size=config.selector_batch_size)`.
- Apply `max_selected` after selector result when positive.
- Run `run_event_pipeline()` for selected items.
- Return summary dict.

- [x] **Step 4: Run tests GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_daily_pipeline_service.py -v
```

Actual:

```text
4 passed in 1.40s
```

偏差与处理：

- 初版测试曾用“先跑一次探测 group id，再跑第二次验证”的方式，导致重复插入同 `source_hash` 并触发唯一约束；已改为单次运行，由 selector 按当前输入候选直接决策。
- 三条测试标题最初过于相似，被候选服务按标题相似度合并成 1 个 group；已改成 OpenAI / NVIDIA / Anthropic 三条不同事件标题。
- 为避免 production path 依赖 monkeypatch 私有 `_load_signals`，实际实现新增 `EditorialCandidateService.build_candidate_groups_from_rows()`。

## Task 3: 一键 CLI

**Files:**
- Create: `apps/worker/scripts/run_daily_pipeline.py`
- Test: `apps/worker/tests/test_run_daily_pipeline_script.py`

- [x] **Step 1: Write failing tests**

已新增测试：

```python
def test_run_daily_pipeline_script_reads_project_env_and_prints_summary(...):
    """验证脚本无参数运行时读取 .env 并输出 summary。"""

def test_run_daily_pipeline_script_does_not_print_database_url_or_api_key(...):
    """验证 stdout 不泄露 DATABASE_URL 或 OPENAI_API_KEY。"""
```

Use temp `.env` via `--env-file` only in tests if needed, or monkeypatch project root. Use SQLite and fake service dependency to avoid real network/LLM.

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_run_daily_pipeline_script.py -v
```

Actual:

```text
ImportError: cannot import name 'run_daily_pipeline' from 'scripts'
2 failed in 0.53s
```

- [x] **Step 3: Implement CLI**

已创建 `scripts/run_daily_pipeline.py`：

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(...)
    parser.add_argument("--env-file", default=None)
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)
    settings = load_settings()
    config = DailyPipelineConfig.from_env(settings)
    engine = create_worker_engine()
    ...
```

Default command:

```powershell
.\.venv\Scripts\python.exe scripts\run_daily_pipeline.py
```

No required parameters.

- [x] **Step 4: Run tests GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_run_daily_pipeline_script.py -v
```

Actual:

```text
2 passed in 1.51s
```

## Task 4: Integration Smoke

**Files:**
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/00-项目总览/项目状态.md`

- [x] **Step 1: Run targeted regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_daily_pipeline_service.py tests/test_run_daily_pipeline_script.py tests/test_config.py -v
```

Actual:

```text
8 passed in 1.81s
```

- [x] **Step 2: Run env smoke**

Run with current project `.env`:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_env_connectivity.py --require-env-file --call-llm
```

Actual:

```json
{"status":"succeeded","env_loaded":true,"database_connected":true,"llm_provider":"openai","llm_model":"gpt-5.5","llm_called":true,"llm_response_ok":true}
```

- [x] **Step 3: Run manual CLI smoke**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\run_daily_pipeline.py
```

Actual:

```json
{
  "status": "succeeded",
  "raw_new_signals_count": 8,
  "candidate_groups_count": 8,
  "selector_mode": "llm",
  "selector_selected_count": 4,
  "selector_rejected_count": 4,
  "selector_manual_review_count": 0,
  "pipeline_runs_count": 4,
  "published_count": 4
}
```

PostgreSQL 后置查询确认：4 个 run 均为 `succeeded`，本轮关联 `agent_runs=12`、`candidates=4`、`dossiers=4`、`reviews=4`、`published=4`。未写入任何 secret。

- [x] **Step 4: Run broader regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py tests/test_run_event_pipeline_script.py tests/test_product_api.py tests/test_product_query_service.py -v
```

Actual:

```text
41 passed in 30.66s
```

- [x] **Step 5: Diff check**

Run:

```powershell
git diff --check
```

Actual:

```text
exit code 0；仅出现 Windows 工作区 LF 将转换为 CRLF 的提示，无 whitespace error
```

## Task 5: Documentation and Commit

**Files:**
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/00-项目总览/项目状态.md`

- [x] **Step 1: Update test record**

Record:

- 执行阶段。
- 改动文件。
- 测试数据。
- 每条命令。
- 真实输出摘要。
- 失败和修复。
- 未覆盖范围。

- [x] **Step 2: Update project status**

Add:

- P1-12 手动 CLI 当前状态。
- 是否已经可以 VS Code / PowerShell 无参数运行。
- 剩余风险。

- [x] **Step 3: Commit**

Do not stage `.env`.

Run:

```powershell
git add .env.example apps/worker/worker/services/daily_pipeline_service.py apps/worker/scripts/run_daily_pipeline.py apps/worker/tests/test_config.py apps/worker/tests/test_daily_pipeline_service.py apps/worker/tests/test_run_daily_pipeline_script.py docs/05-实现计划/P1-12 手动日常全流程CLI设计.md docs/05-实现计划/P1-12 手动日常全流程CLI实施计划.md docs/07-验收与运行/后端P1测试记录.md docs/00-项目总览/项目状态.md
git commit -m "feat(worker): add manual daily pipeline cli"
```

Actual:

```text
commit created；最终 hash 见交付摘要和 `git log -1`
```

## Self Review

- 覆盖设计文档目标：是，Task 2 和 Task 3 分别实现 service 与 CLI。
- 覆盖 `.env` 无参数运行：是，Task 1 和 Task 3。
- 覆盖只处理本轮新增信号：是，Task 2 第一条测试。
- 覆盖文档交付：是，Task 5。
- 不做后台按钮 / 队列 / migration：已在设计和计划中排除。
