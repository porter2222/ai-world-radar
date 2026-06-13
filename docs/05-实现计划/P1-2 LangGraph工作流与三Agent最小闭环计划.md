# P1-2 LangGraph 工作流与三 Agent 最小闭环计划 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 P1-1 新版数据底座之上，用 LangGraph 和确定性三 Agent stub 跑通 `SourceSignal -> EventCandidate -> EventDossier -> ReviewResult -> PublishedEvent` 的最小工作流闭环。

**Architecture:** 本阶段只实现单机 Python Worker 内部的同步工作流，不接真实 LLM，不接 FastAPI，不开发前端。LangGraph 负责节点编排和修订分支，P1-1 的 `SignalService`、`EventService`、`RunLogService` 继续负责所有数据库写入，Agent stub 只返回结构化 schema payload。

**Tech Stack:** Python 3.13, LangGraph 1.2.4, Pydantic 2.13.4, SQLAlchemy 2.0.41, Alembic 1.16.1, PostgreSQL, pytest 8.4.0。

---

## 1. 当前阶段判断

P1-1 已经完成新版后端数据底座，核心链路已经从旧的 `EvidenceCard / EventCluster / Brief` 改为：

```text
SourceSignal
-> EventCandidate
-> EventDossier
-> ReviewResult
-> PublishedEvent
```

P1-2 的任务不是恢复旧 HN pipeline，也不是直接接真实 LLM，而是把 P1-1 的数据底座放进可运行的工作流骨架里。这个骨架必须让后续 P1-3 采集源、P1-4 真实 LLM Agent 和 P1-5 前端页面都能接在正确对象上。

## 2. 本阶段边界

本阶段负责：

- 引入 `langgraph==1.2.4` 并建立导入测试。
- 定义 workflow state schema。
- 新增三类确定性 Agent stub：
  - `OnDutyEditorAgentStub`
  - `ResearchWriterAgentStub`
  - `ReviewPublisherAgentStub`
- 建立工程工具适配层，封装 P1-1 的服务层。
- 实现 LangGraph event pipeline。
- 新增新版脚本入口 `scripts/run_event_pipeline.py`。
- 对旧 `scripts/run_hn_pipeline.py` 做显式 legacy guard，避免后续代理误用旧链路。
- 更新测试记录、计划勾选、项目状态和 HTML 阅读版。

本阶段不负责：

- 不接真实 LLM Agent。
- 不写真实 prompt、repair prompt 或 tool-calling。
- 不做 HN / GitHub 真实采集接入新版链路，这属于 P1-3。
- 不开发 FastAPI、Next.js 前端、后台 UI、Redis、队列、对象存储、向量数据库。
- 不恢复旧 `EvidenceCard / EventCluster / ContentArtifact / QualityGateResult / Brief / BriefItem` 主链路。

## 3. 文件结构

本阶段计划新增或修改以下文件：

```text
apps/worker/pyproject.toml
apps/worker/requirements.txt
apps/worker/tests/test_dependency_imports.py
apps/worker/tests/test_workflow_state.py
apps/worker/tests/test_event_pipeline_agent_stubs.py
apps/worker/tests/test_event_pipeline_tools.py
apps/worker/tests/test_event_pipeline_workflow.py
apps/worker/tests/test_run_event_pipeline_script.py
apps/worker/tests/test_legacy_entrypoints.py
apps/worker/worker/schemas/workflow.py
apps/worker/worker/schemas/__init__.py
apps/worker/worker/agents/event_pipeline_agents.py
apps/worker/worker/agents/__init__.py
apps/worker/worker/tools/__init__.py
apps/worker/worker/tools/event_pipeline_tools.py
apps/worker/worker/workflows/__init__.py
apps/worker/worker/workflows/event_pipeline.py
apps/worker/scripts/run_event_pipeline.py
apps/worker/scripts/run_hn_pipeline.py
docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md
docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.html
docs/07-验收与运行/后端P1测试记录.md
docs/00-项目总览/项目状态.md
docs/00-项目总览/文档索引.md
```

## 4. 设计原则

1. Agent stub 只输出 Pydantic schema，不直接写库。
2. 工作流节点只编排流程，确定性数据库写入通过 tool/service 适配层完成。
3. 所有测试使用 `autoflush=False`，保持和生产 session 工厂一致。
4. P1-2 的 smoke 可以使用预置 demo signal，不接真实 HN API。
5. `pipeline_runs` 的 `signals_count / candidates_count / dossiers_count / published_count / failed_count` 必须由最终数据库结果回填，不能只写过程估计。
6. 代码注释和 docstring 使用中文，至少说明类或函数做什么、输入什么、输出什么。

## 5. Task 1: LangGraph 依赖与导入边界

**Files:**

- Modify: `apps/worker/pyproject.toml`
- Modify: `apps/worker/requirements.txt`
- Modify: `apps/worker/tests/test_dependency_imports.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`

- [x] **Step 1: Write the failing test**

在 `apps/worker/tests/test_dependency_imports.py` 追加：

```python
def test_langgraph_is_available():
    """验证 LangGraph 依赖可以在 worker 环境导入。

    输入：本地 worker 虚拟环境。
    输出：可以导入 StateGraph，并能创建一个最小 graph builder。
    """
    from langgraph.graph import StateGraph

    graph = StateGraph(dict)

    assert graph is not None
```

- [x] **Step 2: Run test to verify RED or local pre-satisfied**

Run:

```powershell
cd "C:\Users\admin\.config\superpowers\worktrees\AI World Radar\p1-data-foundation\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_dependency_imports.py -v
```

Expected if dependency missing:

```text
ModuleNotFoundError: No module named 'langgraph'
```

If this machine already has LangGraph through another dependency path, record the real `passed` output and still add the direct dependency to make migration reproducible.

- [x] **Step 3: Add dependency**

Modify `apps/worker/pyproject.toml`:

```toml
dependencies = [
  "alembic==1.16.1",
  "beautifulsoup4==4.13.4",
  "httpx==0.28.1",
  "langgraph==1.2.4",
  "openai>=1.0.0,<2.0.0",
  "psycopg[binary]==3.2.9",
  "pydantic==2.13.4",
  "python-dotenv==1.1.0",
  "SQLAlchemy==2.0.41",
]
```

Modify `apps/worker/requirements.txt`:

```text
langgraph==1.2.4
pydantic==2.13.4
```

`requirements.txt` 中其他已有依赖保持原样，只补齐 P1-1/P1-2 直接依赖，避免不同安装路径得到不同环境。

- [x] **Step 4: Install and verify GREEN**

Run:

```powershell
cd "C:\Users\admin\.config\superpowers\worktrees\AI World Radar\p1-data-foundation\apps\worker"
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_dependency_imports.py -v
```

Expected:

```text
2 passed
```

执行记录：2026-06-13 在 P1-2 Task 1 首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_dependency_imports.py -v`，真实结果为 `1 failed, 1 passed in 0.35s`，失败点是 `test_langgraph_is_available` 抛出 `ModuleNotFoundError: No module named 'langgraph'`，RED 成立。写入 `langgraph==1.2.4` 到 `pyproject.toml` 和 `requirements.txt` 后执行 `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`，安装日志包含 `Successfully installed ... langgraph-1.2.4 ...`；随后重新运行同一测试，真实结果为 `2 passed in 0.64s`。

- [x] **Step 5: Record and commit**

Update `docs/07-验收与运行/后端P1测试记录.md` with:

- 测试了 LangGraph 导入。
- 测试数据是最小 `StateGraph(dict)`。
- 真实 RED/GREEN 命令输出摘要。
- 是否出现本机依赖已存在的偏差。

Commit:

```powershell
git add apps/worker/pyproject.toml apps/worker/requirements.txt apps/worker/tests/test_dependency_imports.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md
git commit -m "chore(worker): add langgraph dependency"
```

## 6. Task 2: Workflow State Schema

**Files:**

- Create: `apps/worker/worker/schemas/workflow.py`
- Modify: `apps/worker/worker/schemas/__init__.py`
- Create: `apps/worker/tests/test_workflow_state.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`

- [x] **Step 1: Write the failing test**

Create `apps/worker/tests/test_workflow_state.py`:

```python
import pytest
from pydantic import ValidationError

from worker.schemas.workflow import EventPipelineState


def test_workflow_state_tracks_ids_status_and_revision_count():
    """验证工作流状态能记录节点、ID 和修订次数。

    输入：run_id、signal_ids、candidate_id、dossier_id、当前节点和修订次数。
    输出：Pydantic state 保留这些字段，并拒绝超过 P1 上限的修订次数。
    """
    state = EventPipelineState(
        run_id="run_1",
        signal_ids=["sig_1"],
        candidate_ids=["cand_1"],
        dossier_id="dos_1",
        current_node="review_event_dossier",
        revision_count=2,
        status="running",
    )

    assert state.run_id == "run_1"
    assert state.signal_ids == ["sig_1"]
    assert state.candidate_ids == ["cand_1"]
    assert state.dossier_id == "dos_1"
    assert state.revision_count == 2

    with pytest.raises(ValidationError):
        EventPipelineState(revision_count=3)


def test_workflow_state_rejects_unknown_fields():
    """验证工作流状态禁止未知字段。

    输入：包含 unexpected 字段的 state。
    输出：Pydantic 抛出 ValidationError，防止节点随意塞入未约定状态。
    """
    with pytest.raises(ValidationError):
        EventPipelineState(unexpected=True)
```

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workflow_state.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.schemas.workflow'
```

- [x] **Step 3: Implement schema**

Create `apps/worker/worker/schemas/workflow.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from worker.schemas.common import WorkerSchema


EventPipelineStatus = Literal["initialized", "running", "succeeded", "manual_review", "failed"]


class EventPipelineState(WorkerSchema):
    """事件生产工作流状态。

    输入：LangGraph 各节点共享的 run、signal、candidate、dossier、review 和发布状态。
    输出：经过 Pydantic 校验的状态对象，用于节点之间传递和最终验收。
    """

    run_id: str | None = None
    run_key: str | None = None
    trigger_type: str = "manual"
    source_scope: dict[str, Any] = Field(default_factory=dict)
    signal_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    dossier_id: str | None = None
    review_id: str | None = None
    review_decision: str | None = None
    published_event_id: str | None = None
    current_node: str = "initialized"
    revision_count: int = Field(default=0, ge=0, le=2)
    status: EventPipelineStatus = "initialized"
    errors: list[str] = Field(default_factory=list)
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
```

Modify `apps/worker/worker/schemas/__init__.py` to export:

```python
from worker.schemas.workflow import EventPipelineState, EventPipelineStatus
```

- [x] **Step 4: Run test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workflow_state.py -v
```

Expected:

```text
2 passed
```

执行记录：2026-06-13 在 P1-2 Task 2 首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_workflow_state.py -v`，真实结果为 `0 items / 1 error`，失败原因是 `ModuleNotFoundError: No module named 'worker.schemas.workflow'`，RED 成立。新增 `worker/schemas/workflow.py` 并在 `worker/schemas/__init__.py` 导出后重新运行同一测试，真实结果为 `2 passed in 0.10s`。

- [x] **Step 5: Record and commit**

Commit:

```powershell
git add apps/worker/worker/schemas/workflow.py apps/worker/worker/schemas/__init__.py apps/worker/tests/test_workflow_state.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md
git commit -m "feat(worker): define event workflow state"
```

## 7. Task 3: 三 Agent 确定性 Stub

**Files:**

- Create: `apps/worker/worker/agents/event_pipeline_agents.py`
- Modify: `apps/worker/worker/agents/__init__.py`
- Create: `apps/worker/tests/test_event_pipeline_agent_stubs.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`

- [x] **Step 1: Write the failing test**

Create `apps/worker/tests/test_event_pipeline_agent_stubs.py`:

```python
from worker.agents.event_pipeline_agents import (
    OnDutyEditorAgentStub,
    ResearchWriterAgentStub,
    ReviewPublisherAgentStub,
)
from worker.schemas.event import EventCandidateDraft, EventDossierDraft, ReviewResultDraft


def sample_signal():
    """创建 Agent stub 测试用来源信号。

    输入：无。
    输出：包含标题、URL、摘要和热度指标的 dict。
    """
    return {
        "id": "sig_1",
        "source_key": "demo",
        "original_title": "OpenAI releases a new developer tool",
        "original_url": "https://example.com/openai-tool",
        "raw_summary": "Developers discuss the new tool and pricing.",
        "heat_metrics": {"points": 120, "comments": 45},
    }


def test_editor_stub_returns_candidate_draft():
    """验证值班编辑 stub 输出候选事件 schema。

    输入：一条来源信号 dict。
    输出：EventCandidateDraft，包含 candidate_key、标题和评分。
    """
    result = OnDutyEditorAgentStub().triage([sample_signal()])

    assert isinstance(result, EventCandidateDraft)
    assert result.candidate_key == "demo-openai-releases-a-new-developer-tool"
    assert result.ranking_score > 0


def test_writer_stub_returns_dossier_draft_with_source_refs():
    """验证研究写作 stub 输出事件档案 schema。

    输入：候选事件草案和来源信号列表。
    输出：EventDossierDraft，包含中文卡片、详情正文和 source_refs。
    """
    candidate = OnDutyEditorAgentStub().triage([sample_signal()])
    result = ResearchWriterAgentStub().draft(candidate, [sample_signal()])

    assert isinstance(result, EventDossierDraft)
    assert result.candidate_key == candidate.candidate_key
    assert result.source_refs[0]["url"] == "https://example.com/openai-tool"
    assert "中文用户" in result.why_it_matters


def test_reviewer_stub_returns_publish_review_for_complete_dossier():
    """验证审稿发布 stub 对完整 dossier 给出发布建议。

    输入：完整事件档案草案。
    输出：ReviewResultDraft，decision 为 publish 且风险为 low。
    """
    candidate = OnDutyEditorAgentStub().triage([sample_signal()])
    dossier = ResearchWriterAgentStub().draft(candidate, [sample_signal()])
    result = ReviewPublisherAgentStub().review(dossier, revision_count=0)

    assert isinstance(result, ReviewResultDraft)
    assert result.decision == "publish"
    assert result.risk_level == "low"
```

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_agent_stubs.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.agents.event_pipeline_agents'
```

- [x] **Step 3: Implement stubs**

Implement `apps/worker/worker/agents/event_pipeline_agents.py` with:

- `OnDutyEditorAgentStub.triage(signals: list[dict]) -> EventCandidateDraft`
- `ResearchWriterAgentStub.draft(candidate: EventCandidateDraft, signals: list[dict], revision_instructions: str = "") -> EventDossierDraft`
- `ReviewPublisherAgentStub.review(dossier: EventDossierDraft, revision_count: int = 0) -> ReviewResultDraft`

Implementation rules:

- Candidate key uses source key plus normalized first signal title.
- Scores are deterministic from `heat_metrics.points` and `heat_metrics.comments`.
- Dossier text is Chinese and explains “发生了什么、为什么重要、后续看什么”。
- Review returns `publish` for non-empty body and non-empty source refs。
- Review returns `revise` when body or source refs are incomplete and `revision_count < 2`。
- Review returns `manual_review` when incomplete and `revision_count >= 2`。

- [x] **Step 4: Run test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_agent_stubs.py -v
```

Expected:

```text
3 passed
```

执行记录：2026-06-13 在 P1-2 Task 3 首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_agent_stubs.py -v`，真实结果为 `0 items / 1 error`，失败原因是 `ModuleNotFoundError: No module named 'worker.agents.event_pipeline_agents'`，RED 成立。新增 `worker/agents/event_pipeline_agents.py` 并更新 `worker/agents/__init__.py` 后重新运行同一测试，真实结果为 `3 passed in 0.10s`。

- [x] **Step 5: Record and commit**

Commit:

```powershell
git add apps/worker/worker/agents/event_pipeline_agents.py apps/worker/worker/agents/__init__.py apps/worker/tests/test_event_pipeline_agent_stubs.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md
git commit -m "feat(worker): add event pipeline agent stubs"
```

## 8. Task 4: 工程 Tool 适配层

**Files:**

- Create: `apps/worker/worker/tools/__init__.py`
- Create: `apps/worker/worker/tools/event_pipeline_tools.py`
- Create: `apps/worker/tests/test_event_pipeline_tools.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`

- [x] **Step 1: Write the failing test**

Create `apps/worker/tests/test_event_pipeline_tools.py`:

```python
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.models import Base, PublishedEvent
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.tools.event_pipeline_tools import EventPipelineTools


def make_session():
    """创建 tool 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 autoflush=False 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def seed_signal(session):
    """写入一条 tool 可处理的来源信号。

    输入：测试 Session。
    输出：SourceSignal ORM 对象。
    """
    service = SignalService(session)
    service.upsert_source(SourceCreate(source_key="demo", name="Demo", source_type="fixture", fetch_method="manual"))
    return service.upsert_signal(
        SourceSignalCreate(
            source_key="demo",
            source_item_id="demo-1",
            original_title="OpenAI releases a new developer tool",
            original_url="https://example.com/openai-tool",
            raw_summary="Developers discuss the new tool.",
            source_hash="demo:1",
            heat_metrics={"points": 120, "comments": 45},
        )
    )


def test_tools_create_publish_flow_and_update_run_counts():
    """验证工程 tool 通过服务层完成候选、档案、审稿、发布和 run 计数。

    输入：一条 SourceSignal 和确定性 Agent stub。
    输出：PublishedEvent 入库，PipelineRun 计数字段与最终数据库结果一致。
    """
    session = make_session()
    signal = seed_signal(session)
    tools = EventPipelineTools(session)
    run = tools.start_run(run_key="manual-p1-2-tools", source_scope={"source": "demo"})

    signals = tools.load_signals([signal.id])
    candidate = tools.create_candidate(signals)
    dossier = tools.create_dossier(candidate, signals)
    review = tools.review_dossier(dossier)
    published = tools.publish_if_approved(candidate.id, dossier.id, review.decision)
    finished_run = tools.finish_run_with_counts(run.id, status="succeeded", summary="tool smoke")

    assert published is not None
    assert session.scalar(select(PublishedEvent)).id == published.id
    assert finished_run.signals_count == 1
    assert finished_run.candidates_count == 1
    assert finished_run.dossiers_count == 1
    assert finished_run.published_count == 1
    assert finished_run.failed_count == 0
```

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_tools.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.tools'
```

- [x] **Step 3: Implement tools**

Create `EventPipelineTools` with these exact public methods:

- `start_run(run_key: str, source_scope: dict) -> PipelineRun`：调用 `RunLogService.start_pipeline_run` 创建运行记录。
- `load_signals(signal_ids: list[str]) -> list[dict]`：按 ID 读取 `SourceSignal`，转为 Agent stub 输入 dict；任何 ID 不存在时抛出 `ValueError`。
- `create_candidate(signals: list[dict]) -> EventCandidate`：调用 `OnDutyEditorAgentStub.triage` 得到 `EventCandidateDraft`，再调用 `EventService.create_candidate_with_signals` 写入候选事件。
- `create_dossier(candidate: EventCandidate, signals: list[dict], revision_instructions: str = "") -> EventDossier`：调用 `ResearchWriterAgentStub.draft` 得到 `EventDossierDraft`，再调用 `EventService.save_dossier` 写入档案版本。
- `review_dossier(dossier: EventDossier, revision_count: int = 0) -> ReviewResult`：把 `EventDossier` 转为 `EventDossierDraft`，调用 `ReviewPublisherAgentStub.review` 得到 `ReviewResultDraft`，再调用 `EventService.save_review_result` 写入审稿结果。
- `publish_if_approved(candidate_id: str, dossier_id: str, decision: str) -> PublishedEvent | None`：当 `decision == "publish"` 时调用 `EventService.publish_dossier`，其他决策返回 `None`。
- `record_agent_result(run_id: str, agent_name: str, agent_role: str, input_summary: str, output_json: dict, candidate_id: str | None = None, dossier_id: str | None = None, retry_count: int = 0) -> AgentRun`：调用 `RunLogService.record_agent_run` 记录 Agent 输出。
- `finish_run_with_counts(run_id: str, status: str, summary: str, error_message: str | None = None) -> PipelineRun`：查询最终表结果，回填 `PipelineRun` 的 `signals_count / candidates_count / dossiers_count / published_count / failed_count`，再调用 `RunLogService.finish_pipeline_run`。

Implementation must call P1-1 services rather than writing ORM objects directly, except for final count queries that read current database state.

- [x] **Step 4: Run test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_tools.py -v
```

Expected:

```text
1 passed
```

执行记录：2026-06-13 在 P1-2 Task 4 首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_tools.py -v`，真实结果为 `0 items / 1 error`，失败原因是 `ModuleNotFoundError: No module named 'worker.tools'`，RED 成立。新增 `worker/tools/event_pipeline_tools.py` 和 `worker/tools/__init__.py` 后重新运行同一测试，真实结果为 `1 passed in 0.63s`。

- [x] **Step 5: Record and commit**

Commit:

```powershell
git add apps/worker/worker/tools apps/worker/tests/test_event_pipeline_tools.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md
git commit -m "feat(worker): add event pipeline tools"
```

## 9. Task 5: LangGraph Event Pipeline

**Files:**

- Create: `apps/worker/worker/workflows/__init__.py`
- Create: `apps/worker/worker/workflows/event_pipeline.py`
- Create: `apps/worker/tests/test_event_pipeline_workflow.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`

- [x] **Step 1: Write the failing test**

Create `apps/worker/tests/test_event_pipeline_workflow.py`:

```python
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from worker.models import AgentRun, Base, PipelineRun, PublishedEvent
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.workflows.event_pipeline import run_event_pipeline


def make_session():
    """创建 workflow 测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 autoflush=False 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def seed_signal(session):
    """写入一条 workflow 可消费的来源信号。

    输入：测试 Session。
    输出：SourceSignal ORM 对象。
    """
    service = SignalService(session)
    service.upsert_source(SourceCreate(source_key="demo", name="Demo", source_type="fixture", fetch_method="manual"))
    return service.upsert_signal(
        SourceSignalCreate(
            source_key="demo",
            source_item_id="demo-1",
            original_title="OpenAI releases a new developer tool",
            original_url="https://example.com/openai-tool",
            raw_summary="Developers discuss the new tool.",
            source_hash="demo:1",
            heat_metrics={"points": 120, "comments": 45},
        )
    )


def test_langgraph_pipeline_publishes_event_and_records_counts():
    """验证 LangGraph 工作流首跑即可发布事件并记录真实计数。

    输入：一条预置 SourceSignal 和 run_key。
    输出：PublishedEvent、PipelineRun、AgentRun 均入库，PipelineRun 计数等于最终表结果。
    """
    session = make_session()
    signal = seed_signal(session)

    state = run_event_pipeline(
        session,
        signal_ids=[signal.id],
        run_key="manual-p1-2-workflow",
        source_scope={"source": "demo"},
    )

    published_count = len(session.scalars(select(PublishedEvent)).all())
    agent_run_count = len(session.scalars(select(AgentRun)).all())
    run = session.scalar(select(PipelineRun))

    assert state.status == "succeeded"
    assert state.published_event_id is not None
    assert published_count == 1
    assert agent_run_count == 3
    assert run.signals_count == 1
    assert run.candidates_count == 1
    assert run.dossiers_count == 1
    assert run.published_count == published_count
    assert run.failed_count == 0
```

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_workflow.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.workflows'
```

- [x] **Step 3: Implement workflow**

Implement `run_event_pipeline(session, signal_ids, run_key, source_scope=None) -> EventPipelineState`.

Nodes:

```text
collect_signals
-> normalize_signals
-> editorial_triage
-> merge_and_rank_events
-> build_research_package
-> draft_event_dossier
-> review_event_dossier
-> revise_if_needed
-> publish_or_manual_review
-> record_run
```

P1-2 node behavior:

- `collect_signals`：读取传入的 `signal_ids`，不做真实采集。
- `normalize_signals`：确认信号存在并转为 dict。
- `editorial_triage`：调用 `OnDutyEditorAgentStub`，记录 editor agent run。
- `merge_and_rank_events`：调用 tool 创建或更新 `EventCandidate`。
- `build_research_package`：保留来源包在 state trace，不写新表。
- `draft_event_dossier`：调用 `ResearchWriterAgentStub`，保存 `EventDossier`，记录 writer agent run。
- `review_event_dossier`：调用 `ReviewPublisherAgentStub`，保存 `ReviewResult`，记录 reviewer agent run。
- `revise_if_needed`：当审稿为 `revise` 且 `revision_count < 2` 时重新生成 dossier。
- `publish_or_manual_review`：当审稿为 `publish` 时调用 `EventService.publish_dossier`，否则进入 `manual_review`。
- `record_run`：以最终数据库结果更新 `pipeline_runs` 计数并结束 run。

- [x] **Step 4: Run test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_workflow.py -v
```

Expected:

```text
1 passed
```

执行记录：2026-06-13 在 P1-2 Task 5 首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_workflow.py -v`，真实结果为 `0 items / 1 error`，失败原因是 `ModuleNotFoundError: No module named 'worker.workflows'`，RED 成立。新增 `worker/workflows/event_pipeline.py` 和 `worker/workflows/__init__.py` 后重新运行同一测试，真实结果为 `1 passed in 1.14s`。

- [x] **Step 5: Record and commit**

Commit:

```powershell
git add apps/worker/worker/workflows apps/worker/tests/test_event_pipeline_workflow.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md
git commit -m "feat(worker): add langgraph event pipeline"
```

## 10. Task 6: 新版脚本入口与本地 Smoke

**Files:**

- Create: `apps/worker/scripts/run_event_pipeline.py`
- Create: `apps/worker/tests/test_run_event_pipeline_script.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`

- [x] **Step 1: Write the failing test**

Create `apps/worker/tests/test_run_event_pipeline_script.py`:

```python
import json
import subprocess
import sys


def test_run_event_pipeline_script_smoke(tmp_path):
    """验证新版脚本入口可以用 demo signal 跑通首跑发布。

    输入：临时 SQLite 数据库、--create-schema-for-smoke、--seed-demo-signal。
    输出：脚本返回 0，并在 stdout 输出 published_count=1。
    """
    db_path = tmp_path / "p1_2_script_smoke.sqlite"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_event_pipeline.py",
            "--database-url",
            f"sqlite+pysqlite:///{db_path}",
            "--create-schema-for-smoke",
            "--seed-demo-signal",
            "--run-key",
            "manual-p1-2-script",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "succeeded"
    assert summary["published_count"] == 1
```

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_run_event_pipeline_script.py -v
```

Expected:

```text
can't open file
run_event_pipeline.py
```

- [x] **Step 3: Implement script**

Script requirements:

- `--database-url`：覆盖默认数据库 URL。
- `--run-key`：可指定 run key。
- `--create-schema-for-smoke`：仅本地 smoke 使用，调用 `Base.metadata.create_all(engine)`。
- `--seed-demo-signal`：写入一条 demo source 和 source signal。
- 输出 JSON 到 stdout，至少包含：
  - `status`
  - `run_id`
  - `published_event_id`
  - `signals_count`
  - `candidates_count`
  - `dossiers_count`
  - `published_count`

- [x] **Step 4: Run test and manual smoke**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_run_event_pipeline_script.py -v
.\.venv\Scripts\python.exe scripts/run_event_pipeline.py --database-url "sqlite+pysqlite:///scratch/p1_2_smoke.sqlite" --create-schema-for-smoke --seed-demo-signal --run-key "manual-p1-2-smoke"
```

Expected pytest:

```text
1 passed
```

Expected smoke stdout:

```json
{"status":"succeeded","published_count":1}
```

The exact JSON can contain more keys. Record the real stdout in the test record.

执行记录：2026-06-13 在 P1-2 Task 6 首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_run_event_pipeline_script.py -v`，真实结果为 `1 failed in 0.35s`，失败原因是脚本文件不存在，stderr 包含 `can't open file ... scripts\run_event_pipeline.py`。新增 `scripts/run_event_pipeline.py` 后重新运行同一测试，真实结果为 `1 passed in 2.28s`。随后手动 smoke 运行 `.\.venv\Scripts\python.exe scripts/run_event_pipeline.py --database-url "sqlite+pysqlite:///scratch/p1_2_smoke.sqlite" --create-schema-for-smoke --seed-demo-signal --run-key "manual-p1-2-smoke"`，真实 stdout 为 `{"candidates_count": 1, "dossiers_count": 1, "published_count": 1, "published_event_id": "pub_048cfba2a56843c095a71bb7a9d4bf45", "run_id": "run_b5633712541748b9800f54c603534b66", "signals_count": 1, "status": "succeeded"}`。

- [x] **Step 5: Record and commit**

Commit:

```powershell
git add apps/worker/scripts/run_event_pipeline.py apps/worker/tests/test_run_event_pipeline_script.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md
git commit -m "feat(worker): add event pipeline script"
```

## 11. Task 7: 旧入口 Guard 与全量测试恢复

**Files:**

- Modify: `apps/worker/scripts/run_hn_pipeline.py`
- Create: `apps/worker/tests/test_legacy_entrypoints.py`
- Modify: `apps/worker/worker/legacy/README.md`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`

- [x] **Step 1: Write the failing test**

Create `apps/worker/tests/test_legacy_entrypoints.py`:

```python
import subprocess
import sys


def test_old_hn_pipeline_entrypoint_fails_fast_with_legacy_message():
    """验证旧 HN pipeline 入口不会继续误跑旧主链路。

    输入：直接执行 scripts/run_hn_pipeline.py。
    输出：脚本非 0 退出，并提示改用 scripts/run_event_pipeline.py。
    """
    result = subprocess.run(
        [sys.executable, "scripts/run_hn_pipeline.py", "--days", "7", "--limit", "1"],
        check=False,
        text=True,
        capture_output=True,
    )

    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "legacy" in output.lower()
    assert "run_event_pipeline.py" in output
```

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_legacy_entrypoints.py -v
```

Expected before guard:

```text
AssertionError
```

or an import error from old `worker.pipelines.hn_event_pipeline` because old models no longer exist. Either is valid RED if the script does not yet provide the explicit legacy message.

- [x] **Step 3: Implement guard**

Rewrite `apps/worker/scripts/run_hn_pipeline.py` as a small fail-fast script:

```python
from __future__ import annotations

import sys


def main() -> int:
    """提示旧 HN pipeline 已被新版 P1-2 入口替代。

    输入：命令行参数，当前不再解析旧参数。
    输出：向 stderr 输出 legacy 提示，并返回非 0 状态码。
    """
    print(
        "legacy entrypoint: scripts/run_hn_pipeline.py is not part of the P1-2 event dossier pipeline. "
        "Use scripts/run_event_pipeline.py instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

Update `worker/legacy/README.md` to state that old HN pipeline is historical reference only.

- [x] **Step 4: Run test and full worker suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_legacy_entrypoints.py -v
.\.venv\Scripts\python.exe -m pytest -v
```

Expected:

```text
test_legacy_entrypoints.py passed
all worker tests passed
```

Record the exact collected count and duration in `docs/07-验收与运行/后端P1测试记录.md`.

执行记录：2026-06-13 在 P1-2 Task 7 首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_legacy_entrypoints.py -v`，真实结果为 `1 failed in 1.43s`；旧脚本返回非 0，但 stderr 是旧模型 `ImportError: cannot import name 'Brief' from 'worker.db.models'`，没有明确 `legacy` 和 `run_event_pipeline.py` 提示，RED 成立。将 `scripts/run_hn_pipeline.py` 改为 fail-fast legacy guard 并更新 `worker/legacy/README.md` 后运行 `.\.venv\Scripts\python.exe -m pytest tests/test_legacy_boundaries.py tests/test_legacy_entrypoints.py -v`，真实结果为 `3 passed in 0.22s`。随后第一次全量测试为 `1 failed, 41 passed in 4.72s`，失败原因是 legacy README 改写时移除了旧测试要求的精确短语 `not P1-1 entrypoints`；保留该短语并补充 P1-2 说明后，最终全量测试为 `42 passed in 4.37s`。

- [x] **Step 5: Record and commit**

Commit:

```powershell
git add apps/worker/scripts/run_hn_pipeline.py apps/worker/tests/test_legacy_entrypoints.py apps/worker/worker/legacy/README.md docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md
git commit -m "chore(worker): guard legacy hn entrypoint"
```

## 12. Task 8: 最终验收文档与阶段状态

**Files:**

- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`
- Modify: `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.html`
- Modify: `docs/05-实现计划/README.md`
- Modify: `docs/00-项目总览/项目状态.md`
- Modify: `docs/00-项目总览/文档索引.md`

- [ ] **Step 1: Run final verification**

Run:

```powershell
cd "C:\Users\admin\.config\superpowers\worktrees\AI World Radar\p1-data-foundation\apps\worker"
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe scripts/run_event_pipeline.py --database-url "sqlite+pysqlite:///scratch/p1_2_final_smoke.sqlite" --create-schema-for-smoke --seed-demo-signal --run-key "manual-p1-2-final-smoke"
cd ..
cd ..
git diff --check
git status --short --branch
```

Expected:

```text
all worker tests passed
script smoke status=succeeded and published_count=1
git diff --check has no output
```

Use the real command output in the docs. Do not write expected-only results.

- [ ] **Step 2: Update test record**

`docs/07-验收与运行/后端P1测试记录.md` must answer:

- 本次执行的阶段 / task。
- 代码改了哪些模块。
- 测试了什么。
- 测试数据是什么。
- 执行了什么命令。
- 命令真实输出摘要是什么。
- 测试是否通过。
- 失败过哪些测试，以及如何修复。
- 哪些范围没有测试。
- 当前是否可以进入 P1-3。

- [ ] **Step 3: Update plan, status and index**

Update:

- This plan task checkboxes to `[x]` for completed steps.
- `docs/05-实现计划/README.md` with the new P1-2 plan.
- `docs/00-项目总览/项目状态.md` with:
  - 当前分支。
  - P1-2 当前完成度。
  - 已完成的核心能力。
  - 剩余风险。
  - 下一步建议。
- `docs/00-项目总览/文档索引.md` with the new Markdown and HTML plan.

- [ ] **Step 4: Update HTML reading version**

Update `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.html` so it reflects final status and links to the task sections.

- [ ] **Step 5: Commit final docs**

Commit:

```powershell
git add docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.html docs/05-实现计划/README.md docs/00-项目总览/项目状态.md docs/00-项目总览/文档索引.md
git commit -m "docs: record p1-2 workflow acceptance"
```

## 13. 阶段验收标准

P1-2 完成时必须满足：

- `langgraph==1.2.4` 是 worker 直接依赖。
- `tests/test_dependency_imports.py` 覆盖 Pydantic 和 LangGraph 导入。
- `EventPipelineState` 能表达 run、signals、candidate、dossier、review、published event、当前节点、修订次数和最终状态。
- 三 Agent stub 输出 P1-1 schema 兼容 payload。
- LangGraph workflow 首跑可以从预置 `SourceSignal` 生成 `PublishedEvent`。
- `pipeline_runs` 计数字段与最终入库结果一致。
- `agent_runs` 至少记录 editor、writer、reviewer 三类 stub 调用。
- 新脚本入口是 `scripts/run_event_pipeline.py`。
- 旧 `scripts/run_hn_pipeline.py` 有明确 legacy guard。
- worker 全量 pytest 通过。
- 测试记录写清真实命令、真实输出、测试数据、失败修复和未覆盖范围。

## 14. 未覆盖范围

即使 P1-2 完成，仍不覆盖：

- 真实 HN / GitHub 采集接入新版链路。
- 真实 LLM Agent 和 prompt。
- 复杂事实核验。
- 前端首页、详情页和后台管理。
- PostgreSQL 真实临时库 smoke，除非执行代理在 Task 8 额外补充。
- 线上部署和定时调度。

## 15. 执行交接

执行代理必须从 Task 1 开始按顺序推进。每个 task 都要先写测试、运行 RED 或记录本机已满足原因、再实现、再运行 GREEN、更新文档、单独 commit。

Plan complete and saved to `docs/05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`.
