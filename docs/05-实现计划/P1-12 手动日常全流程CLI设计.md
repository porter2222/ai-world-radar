# P1-12 手动日常全流程 CLI 设计

## 1. 背景

当前后端已经具备独立的采集入口和事件生产入口：

- `apps/worker/scripts/collect_source_signals.py`：负责把外部来源写入 `sources` / `source_signals`。
- `apps/worker/scripts/run_event_pipeline.py`：负责从候选池运行 selector，并对 selected group 启动 writer / reviewer / publish。

但这两个入口还不是用户友好的“一键运行”。如果用户想手动跑一次完整链路，目前需要记住多个命令和参数，并且“只处理本轮新增信号”还没有正式入口。此前真实预发布验收使用了临时 harness 才做到本轮新增信号限定，因此需要把该能力产品化。

## 2. 目标

新增一个可以在 VS Code 或 PowerShell 直接运行的 CLI：

```powershell
.\.venv\Scripts\python.exe scripts\run_daily_pipeline.py
```

默认行为：

1. 读取项目根 `.env`。
2. 运行 `daily_all` 采集组。
3. 只处理本轮新增的 `source_signals`。
4. 对本轮新增信号做工程初筛和 candidate grouping。
5. 调用真实 LLM selector。
6. 对 selector selected group 运行 LangGraph writer / reviewer / publish。
7. 输出完整漏斗 JSON。

## 3. 非目标

本阶段不做：

- FastAPI 后台写接口。
- 队列、Redis、Celery、定时调度器。
- 前端后台按钮。
- DailyEdition、历史归档页。
- 新数据库表或 Alembic migration。
- 旧 `EvidenceCard / EventCluster / Brief` 主链路恢复。

## 4. 推荐架构

采用 `DailyPipelineService + CLI`。

### 4.1 Service

新增：

```text
apps/worker/worker/services/daily_pipeline_service.py
```

职责：

- 编排本轮采集和生产流程。
- 记录 `collection_started_at`。
- 基于 `collected_at >= collection_started_at` 查询本轮新增信号。
- 使用 `EditorialCandidateService` 构造 candidate groups。
- 调用 `select_candidate_groups()` 执行 selector。
- 对 selected items 调用 `run_event_pipeline()`。
- 汇总并返回结构化结果。

### 4.2 CLI

新增：

```text
apps/worker/scripts/run_daily_pipeline.py
```

职责：

- 创建 engine / session。
- 从 `.env` 和 `Settings` 读取默认配置。
- 调用 `DailyPipelineService.run_once()`。
- 向 stdout 打印脱敏 JSON summary。
- 用进程退出码表达成功、部分失败或失败。

## 5. 配置

`.env.example` 已补齐以下键：

```env
DAILY_PIPELINE_SOURCE_GROUP=daily_all
DAILY_PIPELINE_LOOKBACK_HOURS=8
DAILY_PIPELINE_SELECTOR_BATCH_SIZE=30
DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR=true
DAILY_PIPELINE_DISABLE_AGENT_FALLBACK=true
```

建议新增并读取：

```env
DAILY_PIPELINE_MAX_SELECTED=5
```

解释：

- 默认最多处理 5 个 selector selected group，避免一次手动运行耗时过长。
- 如果未来要全量处理，可以把该值留空或设置为 `0` 表示不限制。

## 6. 输出契约

成功输出示例：

```json
{
  "status": "succeeded",
  "agent_mode": "llm",
  "collection_started_at": "2026-06-24T05:30:00+00:00",
  "collection_summary": {
    "status": "succeeded",
    "source_keys": ["github_repo_trends", "hn_algolia"],
    "skipped_signals": {"stale": 37, "missing_published_at": 6, "future": 0}
  },
  "raw_new_signals_count": 8,
  "candidate_groups_count": 8,
  "selector_mode": "llm",
  "selector_batches_count": 1,
  "selector_selected_count": 5,
  "selector_rejected_count": 3,
  "selector_manual_review_count": 0,
  "pipeline_runs_count": 5,
  "published_count": 5,
  "run_ids": ["run_xxx"]
}
```

失败输出示例：

```json
{
  "status": "failed",
  "error": "No new source signals collected in this run.",
  "raw_new_signals_count": 0,
  "published_count": 0
}
```

## 7. 状态语义

- `succeeded`：脚本完整运行，且所有 selected pipeline run 均成功。
- `partial_failed`：selector 成功，但部分 pipeline run 失败或进入非成功状态。
- `no_new_signals`：采集成功，但本轮没有新增未处理信号。
- `no_selected_candidates`：工程初筛有候选，但 selector 没有 selected group。
- `failed`：采集、selector 或数据库操作出现未处理异常。

## 8. 性能与耗时

真实 LLM writer / reviewer 是主要耗时来源。基于 2026-06-24 预发布验收，6 个 selected group 可能接近 20 分钟。因此默认 `DAILY_PIPELINE_MAX_SELECTED=5` 更适合手动运行；后续如果需要生产调度，应再引入后台任务或队列，而不是让 HTTP 请求同步等待。

## 9. 后续后台按钮复用

未来后台按钮不应重新实现流程，而应调用同一个 `DailyPipelineService`。按钮层可以只负责：

1. 创建一次 run request。
2. 异步触发 service。
3. 返回 run group id 或 summary id。
4. 前端轮询结果。

本阶段先只做 CLI 和 service，为后续后台按钮保留清晰边界。

## 10. 验收标准

- 用户在 `apps/worker` 下运行 `.\.venv\Scripts\python.exe scripts\run_daily_pipeline.py`，无需额外命令行参数。
- 脚本只依赖项目根 `.env` 和当前数据库。
- 脚本默认只处理本轮新增信号，不消费历史遗留未处理信号。
- stdout JSON 能回答：
  - 本轮新增信号多少。
  - 工程初筛后多少。
  - selector selected / rejected / manual_review 各多少。
  - pipeline run 多少。
  - 最终发布多少。
- 自动化测试覆盖 `.env` 配置读取、无新增信号、selector 无选中、限制 max selected、本轮新增信号过滤和发布计数。
