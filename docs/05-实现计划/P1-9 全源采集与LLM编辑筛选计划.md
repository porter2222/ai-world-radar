# P1-9 全源采集与 LLM 编辑筛选计划 Implementation Plan

> **For agentic workers:** 本计划必须按 TDD 执行。每个代码 task 先写失败测试，再实现，再运行测试通过，最后更新文档并单独提交。

**Goal:** 日常采集当前 13 个信息源，并新增 LLM Editorial Selector，让系统从多来源 `SourceSignal` 中筛出真正值得进入写作和发布的候选事件。

**Architecture:** 本阶段继续沿用新版主链路 `SourceSignal -> EventCandidate -> EventDossier -> ReviewResult -> PublishedEvent`。采集层只写 `sources` / `source_signals`；筛选层只输出结构化候选建议；Agent 不直接写库或发布，状态流转仍由 service / workflow 控制。

**Principle:** 采集求全，展示求精。工程只做稳定硬过滤和去重；“是否值得展示”主要交给 LLM 编辑判断。

---

## 1. 当前阶段

P1-8 已把日常公开源扩展到 13 个 source key。当前缺口是：虽然可以采集多个来源，但生产 pipeline 仍主要通过 `--source-key` 手动消费某一类最新信号，还没有全源采集运行组，也没有跨来源 LLM 编辑筛选。

P1-9 要解决两个问题：

- 日常运行时一键采集全部 13 个 enabled sources。
- 从几十条来源信号中筛选 Top N 候选事件，而不是把所有信号都交给 writer / reviewer。

## 2. 阶段边界

### 负责

- 新增 `daily_all` source group，覆盖当前 13 个 source key。
- 新增基础硬过滤：空标题、空 URL、重复 hash / URL、过旧信号、已处理信号。
- 新增 candidate group 构造：按 canonical URL、repo / product / model 名和标题近似聚合。
- 新增 LLM Editorial Selector，输入 candidate groups，输出 selected / rejected / manual_review 建议。
- 让 pipeline 脚本可以消费 selector 输出的 Top N。
- 更新测试记录、项目状态、文档索引和 HTML 阅读版。

### 不负责

- 不开发前端页面。
- 不做账号池、强反爬、社交平台大爬虫。
- 不做复杂工程热度公式，不为每个 source 维护一套主观权重。
- 不让 LLM 直接写库或发布。
- 不新增数据库表；P1-9 优先复用现有 `source_signals`、`event_candidates`、`pipeline_runs` 和 `agent_runs`。
- 不改变默认 `AGENT_MODE=stub`；真实 LLM 仍需显式开启。

## 3. 当前 13 个信息源

基础源：

```text
hn_algolia
github_releases
github_repo_trends
```

官方 / 平台源：

```text
anthropic_news
aws_machine_learning_blog
deepmind_blog
github_changelog
google_ai_blog
huggingface_blog
nvidia_news
ollama_blog
openai_news
pytorch_blog
```

## 4. 筛选策略

### 4.1 全源采集

日常运行：

```text
all 13 source keys -> source_signals
```

采集层不负责判断“是否展示”，只负责尽量完整地写入来源信号。

### 4.2 工程硬过滤

只做低风险规则：

```text
title 为空 -> 丢弃
url/canonical_url 为空且无法追踪 -> 丢弃
source_hash 重复 -> 去重
canonical_url 重复 -> 合并
published_at/collected_at 超过窗口 -> 默认不进本轮 selector
已有 pipeline_run_id 且没有更新 -> 默认不重复处理
```

### 4.3 Candidate grouping

将多个 signal 合并为同一候选事件组：

```text
同 canonical_url
同 GitHub repo / product / model 名
标题高度相似
同一官方源 + 同一天 + 同主题
HN 讨论指向某个官方发布或 GitHub 项目
```

### 4.4 LLM Editorial Selector

LLM 输入 candidate groups，输出：

```json
{
  "selected": [
    {
      "candidate_group_id": "group_xxx",
      "signal_ids": ["sig_1", "sig_2"],
      "event_title": "...",
      "priority_score": 92,
      "suggested_angle": "...",
      "reason": "官方发布叠加社区讨论，对中文 AI 用户有明显价值"
    }
  ],
  "rejected": [
    {
      "candidate_group_id": "group_yyy",
      "reason": "只是普通版本更新，暂不构成事件"
    }
  ]
}
```

默认策略：

```text
lookback_hours=48
candidate_pool_limit=60
llm_select_top_n=10
pipeline_publish_top_n=5
```

## 5. 任务拆解

### Task 0: Plan and baseline

- [x] **Step 1: Record baseline**

P1-8 后最新 worker 全量回归：

```text
110 passed in 30.44s
```

- [x] **Step 2: Commit plan**

```powershell
git add docs/README.md docs/05-实现计划/README.md docs/05-实现计划/P1-9* docs/00-项目总览/项目状态.md docs/00-项目总览/文档索引.md docs/07-验收与运行/后端P1测试记录.md
git commit -m "docs(worker): add P1-9 all-source editorial selection plan"
```

### Task 1: daily_all source group

- [x] **Step 1: Write failing tests**

覆盖：

- `--source-group daily_all` 可被 CLI 接受。
- fixture mode 会采集当前 13 个 source key。
- `daily_all` 仍只写 `sources` / `source_signals`，不创建 `pipeline_runs` / `published_events`。

- [x] **Step 2: Implement**

新增：

```text
--source-group daily_all
DEFAULT_DAILY_ALL_OFFICIAL_PROFILES
DEFAULT_DAILY_ALL_GITHUB_TREND_QUERIES
DEFAULT_DAILY_ALL_GITHUB_RELEASE_REPOS
```

执行结果：

- 新增 `tests/test_collect_source_signals_script.py::test_collect_source_signals_script_daily_all_group_writes_all_sources_without_pipeline`。
- RED 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py -v`。
- RED 结果：`1 failed, 9 passed in 13.83s`；失败原因是 CLI 仍要求 `--source`，尚未支持 `--source-group daily_all`。
- 实现范围：`scripts/collect_source_signals.py` 新增 `--source-group daily_all`，并展开为 `hn`、`github`、`github_trends`、`official_feeds`；补齐 10 个官方 profile、默认 GitHub release repo 和默认 GitHub trend query。
- GREEN 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py -v`。
- GREEN 结果：`10 passed in 17.67s`。
- 直接 smoke：`.\.venv\Scripts\python.exe scripts\collect_source_signals.py --database-url "sqlite+pysqlite:///scratch/p1_9_daily_all_smoke.sqlite" --create-schema-for-smoke --fixture-mode --source-group daily_all --hn-limit 1 --github-limit 1 --github-trend-limit 1 --official-limit 1 --snapshot-bucket 2026062312`。
- smoke 结果：stdout JSON 返回 `status=succeeded`、`sources_count=13`、`signals_count=13`；后置查询为 `sources=13`、`source_signals=13`、`pipeline_runs=0`、`published_events=0`。
- 最终全量回归：`.\.venv\Scripts\python.exe -m pytest -v`，结果为 `111 passed in 31.43s`。
- 验证结论：fixture 模式一次写入 13 个 source key 和 13 条 `source_signals`，且 `pipeline_runs=0`、`published_events=0`。

### Task 2: hard filter and candidate grouping

- [x] **Step 1: Write failing tests**

覆盖：

- 空标题 / 无 URL 信号不会进入 selector。
- 同 canonical_url 合并为一个 group。
- 同 repo / 标题近似可合并为一个 group。
- 已处理 `pipeline_run_id` 默认不重复进入 selector。

- [x] **Step 2: Implement service**

新增：

```text
worker/services/editorial_candidate_service.py
```

执行结果：

- 新增 `tests/test_editorial_candidate_service.py`，使用内存 SQLite 和生产一致的 `autoflush=False` Session 构造 source signal 测试数据。
- 第一段 RED 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_editorial_candidate_service.py -v`。
- 第一段 RED 结果：`1 error in 0.84s`；失败原因是 `worker.services.editorial_candidate_service` 尚不存在。
- 实现范围：新增 `EditorialCandidateService` 和 `EditorialCandidateGroup`，从 `source_signals` 读取信号，执行硬过滤与内存分组，不写数据库、不发布事件。
- 追加 lookback RED：临时移除时间窗口判断后运行同一测试，结果为 `1 failed, 4 passed in 1.00s`；失败原因是 5 天前旧信号仍进入候选 group。
- GREEN 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_editorial_candidate_service.py -v`。
- GREEN 结果：`5 passed in 0.63s`。
- 最终全量回归：`.\.venv\Scripts\python.exe -m pytest -v`，结果为 `116 passed in 36.87s`。
- 覆盖结论：空标题、无 URL、已处理 `pipeline_run_id`、超过 lookback 窗口的旧信号不会进入 selector；同 canonical URL、同 GitHub repo、标题近似的信号会合并为同一 group。

### Task 3: LLM Editorial Selector

- [x] **Step 1: Write failing tests**

覆盖：

- fake LLM 可以返回 selected / rejected 结构化输出。
- 输出必须包含 priority_score、reason、suggested_angle。
- LLM 只能输出建议，不能直接写库或发布。

- [x] **Step 2: Implement agent**

新增：

```text
worker/agents/editorial_selector_agent.py
worker/schemas/editorial_selection.py
```

执行结果：

- 新增 `tests/test_editorial_selector_agent.py`，用 fake LLM 覆盖 selected / rejected / manual_review 输出、selected 必填解释字段和 prompt 越权边界。
- RED 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_editorial_selector_agent.py -v`。
- RED 结果：`1 error in 0.37s`；失败原因是 `worker.agents.editorial_selector_agent` 尚不存在。
- 实现范围：新增 `worker/schemas/editorial_selection.py`，定义 `EditorialSelectionResult`、selected/rejected/manual_review item；新增 `EditorialSelectorLLMAgent`，复用 `LLMJsonAgent` 结构化 JSON 调用。
- GREEN 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_editorial_selector_agent.py -v`。
- GREEN 结果：`3 passed in 0.11s`。
- 最终全量回归：`.\.venv\Scripts\python.exe -m pytest -v`，结果为 `119 passed in 83.79s (0:01:23)`。
- 验证结论：selector 能返回 selected / rejected / manual_review；selected 项必须包含 `priority_score`、`reason`、`suggested_angle`；prompt 明确包含“只能输出编辑筛选建议、不要写数据库、不要直接发布、不要修改 source_signals”。

### Task 4: Pipeline script consumes selector output

- [ ] **Step 1: Write failing tests**

覆盖：

- `run_event_pipeline.py --select-top-candidates 5` 从 selector 输出中启动 pipeline。
- 只对 selected group 运行 writer / reviewer。
- rejected group 不写 `published_events`。

- [ ] **Step 2: Implement script integration**

保持默认 `AGENT_MODE=stub`，真实 LLM 需要显式开启。

## 6. 验收标准

- `collect_source_signals.py --source-group daily_all --fixture-mode` 可采集当前 13 个 source key。
- selector 前硬过滤和 grouping 有单测。
- LLM Editorial Selector 有 fake LLM 回归测试。
- pipeline 只处理 selector 选中的 Top N。
- 采集层不误创建 pipeline 或发布。
- 文档记录真实命令、真实输出、失败修复和未覆盖范围。

## 7. 风险

- 13 源全采会增加网络失败概率，脚本需要清晰报告失败 profile。
- LLM selector 成本需要控制，必须限制 candidate_pool_limit。
- LLM 输出可能波动，必须记录 agent_runs 便于审计。
- 本阶段不做复杂事实核验，只判断事件价值和展示优先级。
