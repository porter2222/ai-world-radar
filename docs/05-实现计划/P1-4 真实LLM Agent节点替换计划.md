# P1-4 真实 LLM Agent 节点替换计划 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 每个 task 必须先写测试、运行 RED、再写实现、运行 GREEN、更新文档并单独提交。

**Goal:** 在 P1-1 数据底座、P1-2 LangGraph 工作流、P1-3 HN / GitHub 采集接入已完成的基础上，把值班编辑、研究写作、审稿发布三个确定性 stub 逐个替换为真实 LLM Agent。

**Architecture:** P1-4 不改变新版主链路，也不新增数据库表。真实 LLM Agent 只替换 `EventPipelineTools` 中的 editor / writer / reviewer 注入对象，仍输出 Pydantic 契约，由服务层负责写库、状态流转、发布和计数。LLM 调用统一经过现有 `LLMClient`，provider / model / key / base_url 均来自 `.env` 或环境变量，测试使用 fake client，不依赖真实网络。

**Tech Stack:** Python 3.13, OpenAI-compatible SDK, Pydantic 2.13.4, SQLAlchemy 2.0.41, LangGraph 1.2.4, pytest 8.4.0。

---

## 1. 当前阶段

P1-1 已完成新版后端数据底座，P1-2 已完成 LangGraph 工作流和三 Agent 确定性 stub，P1-3 已完成 HN / GitHub source layer 接入。

当前唯一主链路仍是：

```text
SourceSignal
-> EventCandidate
-> EventDossier
-> ReviewResult
-> PublishedEvent
```

P1-4 的任务不是重写 pipeline，而是在这个主链路上替换 Agent 判断和生成能力。

## 2. 阶段边界

### 负责

- 真实 LLM Agent 结构化 JSON 调用基座。
- 值班编辑 LLM Agent：输出 `EventCandidateDraft`。
- 研究写作 LLM Agent：输出 `EventDossierDraft`。
- 审稿发布 LLM Agent：输出 `ReviewResultDraft`。
- Agent factory 与 `--agent-mode stub|llm` 脚本入口。
- `agent_runs` 记录 provider、model、prompt_version、retry_count 和必要 trace。
- fake LLM 回归测试和可选真实 provider smoke。
- 更新测试记录、项目状态、文档索引和 HTML 阅读版。

### 不负责

- 不恢复 `EvidenceCard / EventCluster / ContentArtifact / QualityGateResult / Brief / BriefItem` 旧链路。
- 不让 Agent 直接写数据库、直接发布、直接隐藏或删除数据。
- 不实现自由上网、搜索工具、RAG、向量数据库、Redis、队列、对象存储或后台 UI。
- 不做完整事实核验；审稿 Agent 只做来源支撑、过度推断、中文表达和风险提示。
- 不把 API key、真实 token、账号密码或 provider 私密配置写入代码或文档。
- 不把 GitHub Trending HTML 抓取纳入 P1-4。

## 3. 文件结构

本阶段预计新增或修改：

```text
apps/worker/worker/agents/llm_json_agent.py
apps/worker/worker/agents/llm_event_pipeline_agents.py
apps/worker/worker/agents/factory.py
apps/worker/worker/agents/__init__.py
apps/worker/worker/config.py
apps/worker/worker/tools/event_pipeline_tools.py
apps/worker/worker/workflows/event_pipeline.py
apps/worker/scripts/run_event_pipeline.py
apps/worker/scripts/smoke_llm_event_pipeline.py
apps/worker/tests/test_llm_json_agent.py
apps/worker/tests/test_llm_editor_agent.py
apps/worker/tests/test_llm_writer_agent.py
apps/worker/tests/test_llm_reviewer_agent.py
apps/worker/tests/test_agent_factory.py
apps/worker/tests/test_run_event_pipeline_script.py
apps/worker/tests/test_event_pipeline_llm_mode.py
docs/07-验收与运行/后端P1测试记录.md
docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md
docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.html
docs/05-实现计划/README.md
docs/00-项目总览/项目状态.md
docs/00-项目总览/文档索引.md
docs/README.md
```

## 4. 设计口径

### 4.1 LLM Agent 调用基座

新增 `LLMJsonAgent`，只负责三件事：

1. 组装 system / user prompt。
2. 调用 `LLMClient.chat`。
3. 从模型文本中提取 JSON，并用目标 Pydantic schema 校验。

失败处理：

- 第一次输出不是 JSON 或 schema 校验失败时，最多追加 2 次 repair prompt。
- 每次 repair prompt 必须包含错误摘要、原始输出和目标 JSON 要求。
- 仍失败时抛出 `LLMAgentOutputError`，由 workflow 或脚本层记录失败。

### 4.2 Agent 输出契约

真实 LLM Agent 必须继续输出既有 schema：

- 值班编辑：`EventCandidateDraft`
- 研究写作：`EventDossierDraft`
- 审稿发布：`ReviewResultDraft`

不新增 `EvidenceCard`、`EventCluster`、`Brief` 等旧对象。

### 4.3 Agent 运行记录

`agent_runs` 已有以下字段，P1-4 不需要新增 migration：

- `model_provider`
- `model_name`
- `prompt_version`
- `output_json`
- `trace_json`
- `retry_count`
- `error_message`

P1-4 需要把真实 LLM Agent 的 provider、model、prompt version、retry count 写入这些字段。

### 4.4 模式开关

默认模式仍是 stub，避免本地无 API key 时破坏现有回归：

```text
AGENT_MODE=stub
```

真实 LLM 模式通过 `.env` 或脚本参数开启：

```powershell
.\.venv\Scripts\python.exe scripts\run_event_pipeline.py --source-key hn_algolia --limit 1 --agent-mode llm
```

## 5. 任务拆解

### Task 0: P1-4 计划与入口文档

**Files:**

- Create: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`
- Create: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.html`
- Modify: `docs/README.md`
- Modify: `docs/05-实现计划/README.md`
- Modify: `docs/00-项目总览/项目状态.md`
- Modify: `docs/00-项目总览/文档索引.md`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`

- [x] **Step 1: Write plan and HTML reading version**

写入本计划和对应 HTML，让后续代理能只读文档理解 P1-4 的目标、边界、任务顺序和验收方式。

执行记录：已新增本计划 Markdown、HTML 阅读版，并同步更新 `docs/README.md`、`docs/05-实现计划/README.md`、`docs/00-项目总览/项目状态.md`、`docs/00-项目总览/文档索引.md` 和 `docs/07-验收与运行/后端P1测试记录.md`。

- [x] **Step 2: Run documentation checks**

Run:

```powershell
git diff --check
rg "待[补]充|占[位]|预[计]通过|应[该]通过" docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md docs/07-验收与运行/后端P1测试记录.md
```

Expected:

```text
git diff --check 无 trailing whitespace 或冲突标记错误
rg 无匹配
```

执行记录：已运行 `git diff --check`，真实结果为退出码 0；PowerShell 输出为 Windows 工作区 LF/CRLF 提示，没有 trailing whitespace 或冲突标记错误。已运行 `rg "待[补]充|占[位]|预[计]通过|应[该]通过" docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md docs/07-验收与运行/后端P1测试记录.md`，真实结果为退出码 1、无匹配。

- [x] **Step 3: Commit**

```powershell
git add docs/README.md docs/05-实现计划/README.md docs/05-实现计划/P1-4* docs/00-项目总览/项目状态.md docs/00-项目总览/文档索引.md docs/07-验收与运行/后端P1测试记录.md
git commit -m "docs: add p1-4 llm agent replacement plan"
```

执行记录：本 task 的文档计划提交为 `docs: add p1-4 llm agent replacement plan`。

### Task 1: LLM JSON Agent Base

**Files:**

- Create: `apps/worker/tests/test_llm_json_agent.py`
- Create: `apps/worker/worker/agents/llm_json_agent.py`
- Modify: `apps/worker/worker/agents/__init__.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`

- [x] **Step 1: Write failing tests**

测试文件必须覆盖：

```python
def test_llm_json_agent_parses_fenced_json_into_schema():
    """验证 LLMJsonAgent 能提取 fenced JSON 并校验为 Pydantic schema。"""


def test_llm_json_agent_repairs_invalid_json_once():
    """验证第一次输出非法时会带错误摘要重试，并返回 retry_count=1。"""


def test_llm_json_agent_raises_after_max_retries():
    """验证多次修复失败后抛出 LLMAgentOutputError。"""
```

测试使用 fake LLMClient，不访问网络。

执行记录：已新增 `apps/worker/tests/test_llm_json_agent.py`，覆盖 fenced JSON 解析、非法 JSON repair 一次成功、超过最大 repair 次数抛出 `LLMAgentOutputError`。测试使用 `FakeLLMClient`，不访问真实 provider。

- [x] **Step 2: Run RED**

Run:

```powershell
cd apps/worker
.\.venv\Scripts\python.exe -m pytest tests/test_llm_json_agent.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'worker.agents.llm_json_agent'
```

执行记录：首次运行 `.\.venv\Scripts\python.exe -m pytest tests/test_llm_json_agent.py -v`，真实结果为 `collected 0 items / 1 error`，失败原因为 `ModuleNotFoundError: No module named 'worker.agents.llm_json_agent'`，RED 成立。

- [x] **Step 3: Implement LLM JSON base**

新增：

```python
class LLMAgentOutputError(ValueError):
    """表示 LLM 输出无法解析为目标 schema。"""


class LLMJsonResult:
    """封装结构化输出、原文和重试次数。"""


class LLMJsonAgent:
    """真实 LLM Agent 的结构化 JSON 调用基座。"""
```

核心行为：

- `run_json(schema_type, system_prompt, user_prompt) -> LLMJsonResult`
- 支持纯 JSON 和 fenced JSON。
- 使用 `model_validate` 校验目标 schema。
- repair 最多 2 次。
- 每个函数写中文 docstring，说明输入和输出。

执行记录：已新增 `apps/worker/worker/agents/llm_json_agent.py`，包含 `LLMAgentOutputError`、`LLMJsonResult`、`LLMJsonAgent` 和 `_extract_json_text`；已更新 `apps/worker/worker/agents/__init__.py` 导出。每个类和函数均写入中文 docstring，说明输入与输出。

- [x] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_json_agent.py -v
```

Expected:

```text
3 passed
```

执行记录：重新运行 `.\.venv\Scripts\python.exe -m pytest tests/test_llm_json_agent.py -v`，真实结果为 `3 passed in 0.13s`。随后运行 `.\.venv\Scripts\python.exe -m pytest tests/test_llm_json_agent.py tests/test_event_pipeline_agent_stubs.py -v`，真实结果为 `6 passed in 0.14s`。

- [x] **Step 5: Commit**

```powershell
git add apps/worker/tests/test_llm_json_agent.py apps/worker/worker/agents/llm_json_agent.py apps/worker/worker/agents/__init__.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-4*
git commit -m "feat(worker): add llm json agent base"
```

执行记录：本 task 的提交为 `feat(worker): add llm json agent base`。

### Task 2: On-duty Editor LLM Agent

**Files:**

- Create: `apps/worker/tests/test_llm_editor_agent.py`
- Create or Modify: `apps/worker/worker/agents/llm_event_pipeline_agents.py`
- Modify: `apps/worker/worker/agents/__init__.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`

- [ ] **Step 1: Write failing tests**

测试文件必须覆盖：

```python
def test_on_duty_editor_llm_agent_returns_candidate_draft():
    """验证值班编辑 LLM Agent 把来源信号转为 EventCandidateDraft。"""


def test_on_duty_editor_prompt_forbids_database_and_publish_actions():
    """验证 prompt 明确要求 Agent 不写数据库、不发布、不删除信号。"""
```

fake LLM 返回字段：

```json
{
  "candidate_key": "hn-openai-agent",
  "title": "OpenAI 新编码 Agent 引发开发者关注",
  "event_type": "product_update",
  "category": "模型与产品",
  "primary_subject": "OpenAI",
  "suggested_angle": "从开发者工作流变化解释这件事。",
  "heat_score": 75,
  "importance_score": 82,
  "audience_value_score": 78,
  "ranking_score": 79,
  "ranking_reason": "HN 讨论热度和开发者使用价值同时存在。",
  "merge_reason": "当前信号可单独形成候选事件。"
}
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_editor_agent.py -v
```

Expected:

```text
ImportError 或 AttributeError，OnDutyEditorLLMAgent 尚不存在
```

- [ ] **Step 3: Implement editor agent**

新增：

```python
class OnDutyEditorLLMAgent:
    """值班编辑真实 LLM Agent。"""

    name = "on_duty_editor_llm"
    role = "editor"
    prompt_version = "p1-4-editor-v1"

    def triage(self, signals: list[dict[str, Any]]) -> EventCandidateDraft:
        """输入标准化 source signals，输出 EventCandidateDraft。"""
```

prompt 必须包含：

- 中文输出。
- 只输出 JSON。
- 不写数据库。
- 不直接发布。
- 不删除或隐藏信号。
- 不做完整事实核验。
- 分数必须为 0 到 100。

- [ ] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_editor_agent.py tests/test_llm_json_agent.py -v
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/tests/test_llm_editor_agent.py apps/worker/worker/agents/llm_event_pipeline_agents.py apps/worker/worker/agents/__init__.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-4*
git commit -m "feat(worker): add on-duty editor llm agent"
```

### Task 3: Research Writer LLM Agent

**Files:**

- Create: `apps/worker/tests/test_llm_writer_agent.py`
- Modify: `apps/worker/worker/agents/llm_event_pipeline_agents.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`

- [ ] **Step 1: Write failing tests**

测试文件必须覆盖：

```python
def test_research_writer_llm_agent_returns_event_dossier_draft():
    """验证研究写作 LLM Agent 输出 EventDossierDraft。"""


def test_research_writer_receives_revision_instructions():
    """验证审稿修订意见会进入写作 prompt。"""
```

fake LLM 返回 `card_title`、`card_summary`、`detail_title`、`detail_summary`、`detail_body`、`why_it_matters`、`follow_up_points`、`source_refs` 和 `status`。

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_writer_agent.py -v
```

Expected:

```text
ImportError 或 AttributeError，ResearchWriterLLMAgent 尚不存在
```

- [ ] **Step 3: Implement writer agent**

新增：

```python
class ResearchWriterLLMAgent:
    """研究写作真实 LLM Agent。"""

    name = "research_writer_llm"
    role = "writer"
    prompt_version = "p1-4-writer-v1"

    def draft(
        self,
        candidate: EventCandidateDraft,
        signals: list[dict[str, Any]],
        revision_instructions: str = "",
    ) -> EventDossierDraft:
        """输入候选事件、来源信号和修订意见，输出 EventDossierDraft。"""
```

prompt 必须包含：

- 面向中文用户。
- 不编造来源没有支撑的信息。
- `card_summary` 控制在 120 字符以内。
- `source_refs` 必须引用输入 signal。
- revision instructions 为空时不生成修订说明；非空时必须纳入重写要求。

- [ ] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_writer_agent.py tests/test_llm_json_agent.py -v
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/tests/test_llm_writer_agent.py apps/worker/worker/agents/llm_event_pipeline_agents.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-4*
git commit -m "feat(worker): add research writer llm agent"
```

### Task 4: Review Publisher LLM Agent

**Files:**

- Create: `apps/worker/tests/test_llm_reviewer_agent.py`
- Modify: `apps/worker/worker/agents/llm_event_pipeline_agents.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`

- [ ] **Step 1: Write failing tests**

测试文件必须覆盖：

```python
def test_review_publisher_llm_agent_returns_publish_review():
    """验证审稿发布 LLM Agent 可输出 publish 决策。"""


def test_review_publisher_prompt_lists_allowed_decisions():
    """验证 prompt 明确限定 publish、revise、manual_review、reject。"""
```

fake LLM 返回：

```json
{
  "decision": "publish",
  "risk_level": "low",
  "issues": [],
  "revision_instructions": "",
  "checked_items": {
    "source_supported": true,
    "not_overstated": true,
    "has_chinese_context": true
  }
}
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_reviewer_agent.py -v
```

Expected:

```text
ImportError 或 AttributeError，ReviewPublisherLLMAgent 尚不存在
```

- [ ] **Step 3: Implement reviewer agent**

新增：

```python
class ReviewPublisherLLMAgent:
    """审稿发布真实 LLM Agent。"""

    name = "review_publisher_llm"
    role = "reviewer"
    prompt_version = "p1-4-reviewer-v1"

    def review(self, dossier: EventDossierDraft, revision_count: int = 0) -> ReviewResultDraft:
        """输入事件档案草案和修订次数，输出 ReviewResultDraft。"""
```

prompt 必须包含：

- 只能输出 `publish`、`revise`、`manual_review`、`reject`。
- 不直接发布。
- 不改写正文。
- 检查来源支撑、过度推断、空泛表达和标题党风险。
- 当风险不确定时选择 `manual_review`。

- [ ] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_reviewer_agent.py tests/test_llm_json_agent.py -v
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/tests/test_llm_reviewer_agent.py apps/worker/worker/agents/llm_event_pipeline_agents.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-4*
git commit -m "feat(worker): add review publisher llm agent"
```

### Task 5: Agent Factory, Workflow Injection, and CLI Mode

**Files:**

- Create: `apps/worker/tests/test_agent_factory.py`
- Modify: `apps/worker/tests/test_event_pipeline_llm_mode.py`
- Modify: `apps/worker/tests/test_run_event_pipeline_script.py`
- Create: `apps/worker/worker/agents/factory.py`
- Modify: `apps/worker/worker/config.py`
- Modify: `apps/worker/worker/tools/event_pipeline_tools.py`
- Modify: `apps/worker/worker/workflows/event_pipeline.py`
- Modify: `apps/worker/scripts/run_event_pipeline.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`

- [ ] **Step 1: Write failing tests**

测试必须覆盖：

```python
def test_create_event_agents_defaults_to_stub_mode():
    """验证默认 agent mode 是 stub，避免无 API key 环境破坏回归。"""


def test_create_event_agents_llm_mode_returns_llm_agents_with_shared_client():
    """验证 llm mode 创建三类真实 LLM Agent。"""


def test_event_pipeline_can_run_with_injected_llm_agents():
    """验证 workflow 可通过注入 fake LLM agents 跑通，不依赖真实网络。"""


def test_run_event_pipeline_script_accepts_agent_mode_argument():
    """验证脚本接受 --agent-mode stub|llm。"""
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_factory.py tests/test_event_pipeline_llm_mode.py tests/test_run_event_pipeline_script.py -v
```

Expected:

```text
agent factory 不存在，或 --agent-mode 参数不存在
```

- [ ] **Step 3: Implement factory and injection**

新增：

```python
@dataclass(frozen=True)
class EventAgentSet:
    """封装事件 pipeline 使用的三类 Agent。"""


def create_event_agents(mode: str = "stub", llm_client: LLMClient | None = None) -> EventAgentSet:
    """输入 agent mode 和可选 LLMClient，输出三类 Agent 实例。"""
```

修改：

- `Settings` 增加 `agent_mode: str`，读取 `AGENT_MODE`，默认 `stub`。
- `run_event_pipeline` 增加可选 `agent_mode` 或 `tools` 注入参数。
- `scripts/run_event_pipeline.py` 增加 `--agent-mode stub|llm`，默认读取 settings。
- stub 模式继续完全兼容现有测试。

- [ ] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_factory.py tests/test_event_pipeline_llm_mode.py tests/test_run_event_pipeline_script.py -v
```

Expected:

```text
全部通过
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/tests/test_agent_factory.py apps/worker/tests/test_event_pipeline_llm_mode.py apps/worker/tests/test_run_event_pipeline_script.py apps/worker/worker/agents/factory.py apps/worker/worker/config.py apps/worker/worker/tools/event_pipeline_tools.py apps/worker/worker/workflows/event_pipeline.py apps/worker/scripts/run_event_pipeline.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-4*
git commit -m "feat(worker): add llm agent mode to event pipeline"
```

### Task 6: Agent Run Metadata and Failure Recording

**Files:**

- Modify: `apps/worker/tests/test_event_pipeline_llm_mode.py`
- Modify: `apps/worker/worker/tools/event_pipeline_tools.py`
- Modify: `apps/worker/worker/agents/llm_json_agent.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`

- [ ] **Step 1: Write failing tests**

测试必须覆盖：

```python
def test_llm_agent_runs_record_provider_model_prompt_and_retry_count():
    """验证 agent_runs 记录真实 LLM metadata。"""


def test_llm_agent_failure_records_failed_agent_run():
    """验证 LLM 输出持续失败时记录 failed agent_run 和错误摘要。"""
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_llm_mode.py -v
```

Expected:

```text
model_provider / model_name / prompt_version / retry_count 未写入，或失败记录不存在
```

- [ ] **Step 3: Implement metadata recording**

实现要求：

- `LLMJsonResult` 暴露 `retry_count`、`raw_text`、`prompt_version`。
- LLM Agent 暴露 `model_provider`、`model_name`、`prompt_version`。
- `EventPipelineTools.record_agent_result` 写入 provider、model、prompt_version、retry_count。
- 当 LLM Agent 抛出 `LLMAgentOutputError` 时，记录 `status="failed"` 的 `agent_runs`，再让 workflow 进入 failed 或脚本返回 failed JSON。

- [ ] **Step 4: Run GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_event_pipeline_llm_mode.py tests/test_run_log_service.py -v
```

Expected:

```text
全部通过
```

- [ ] **Step 5: Commit**

```powershell
git add apps/worker/tests/test_event_pipeline_llm_mode.py apps/worker/worker/tools/event_pipeline_tools.py apps/worker/worker/agents/llm_json_agent.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-4*
git commit -m "feat(worker): record llm agent run metadata"
```

### Task 7: P1-4 Smoke, Docs, and Phase Handoff

**Files:**

- Create: `apps/worker/scripts/smoke_llm_event_pipeline.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`
- Modify: `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.html`
- Modify: `docs/05-实现计划/README.md`
- Modify: `docs/00-项目总览/项目状态.md`
- Modify: `docs/00-项目总览/文档索引.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Add smoke helper**

新增脚本：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_llm_event_pipeline.py --fixture-mode
.\.venv\Scripts\python.exe scripts\smoke_llm_event_pipeline.py --call-real-provider
```

`--fixture-mode` 使用 fake LLM，不访问网络；`--call-real-provider` 使用 `.env` 中 provider 配置，真实调用失败时必须原文记录错误。

- [ ] **Step 2: Run full worker pytest**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected:

```text
all tests passed
```

- [ ] **Step 3: Run fake LLM smoke**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_llm_event_pipeline.py --fixture-mode
```

Expected:

```text
status=succeeded
agent_mode=llm
published_count=1
```

- [ ] **Step 4: Run optional real provider smoke**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_llm_event_pipeline.py --call-real-provider
```

Expected:

```text
若 .env 可用且 provider 正常，输出 status=succeeded。
若 provider/gateway 失败，记录真实错误，且不把失败伪装为通过。
```

- [ ] **Step 5: Update docs with real outputs**

`docs/07-验收与运行/后端P1测试记录.md` 必须写清：

- 本次执行阶段 / task。
- 代码改了哪些模块。
- 测试了什么。
- 测试数据是什么。
- 执行命令是什么。
- 命令真实输出摘要是什么。
- 失败过哪些测试，以及如何修复。
- 哪些范围没有覆盖。
- 当前是否可以进入 P1-5。

- [ ] **Step 6: Run documentation checks**

Run:

```powershell
git diff --check
rg "待[补]充|占[位]|预[计]通过|应[该]通过" docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md
```

Expected:

```text
git diff --check 无 trailing whitespace 或冲突标记错误
rg 无匹配
```

- [ ] **Step 7: Commit**

```powershell
git add apps/worker/scripts/smoke_llm_event_pipeline.py docs/07-验收与运行/后端P1测试记录.md docs/05-实现计划/P1-4* docs/05-实现计划/README.md docs/00-项目总览/项目状态.md docs/00-项目总览/文档索引.md docs/README.md
git commit -m "docs: record p1-4 llm agent acceptance"
```

## 6. 验收标准

P1-4 完成后必须满足：

- stub 模式仍是默认模式，且不需要 API key。
- LLM 模式可以通过 `--agent-mode llm` 或 `AGENT_MODE=llm` 开启。
- 三类 LLM Agent 均通过 fake LLM 测试输出既有 Pydantic schema。
- LangGraph workflow 在注入 fake LLM agents 时能首跑生成 `PublishedEvent`。
- `agent_runs` 能记录 provider、model、prompt_version、retry_count、output_json 和 trace_json。
- LLM 输出非法时能 repair；持续失败时能记录失败并返回明确错误。
- worker 全量 pytest 通过。
- fake LLM smoke 证明“已采集信号 -> LLM Agent -> 审稿 -> 发布快照”首跑可用。
- 真实 provider smoke 已执行并记录真实结果；若失败，必须写明 provider/gateway 错误，不能写成通过。
- 文档记录真实命令、真实输出、测试数据、失败修复、未覆盖范围和是否可以进入 P1-5。

## 7. 风险与处理方式

- Provider/gateway 可能失败：自动化回归只依赖 fake LLM；真实 provider smoke 单独记录，不作为本地无 key 环境的阻塞条件。
- LLM 输出不稳定：通过 JSON extraction、Pydantic validation、repair prompt 和最大重试次数收敛。
- Agent 可能过度推断：writer prompt 必须要求来源支撑，reviewer prompt 必须检查过度推断；P1-4 不声明完整事实核验。
- 成本风险：P1-4 默认 stub，真实调用需要显式 `--agent-mode llm` 或 `--call-real-provider`。
- 发布风险：Agent 不直接发布，只给结构化建议；发布仍由 `EventService.publish_dossier` 控制。

## 8. 执行交接

本计划保存于 `docs/05-实现计划/P1-4 真实LLM Agent节点替换计划.md`。当前建议按 Task 0 到 Task 7 顺序执行，每个 task 单独 RED/GREEN、更新文档并提交。
