# P1-6 产品接口层与最小 API 计划

> **当前状态：P1-6 Task 1 到 Task 3 已完成。当前已有 `ProductQueryService`、FastAPI 只读适配层和 PostgreSQL 产品查询 smoke。**

**Goal:** 在 P1-1 到 P1-5 后端生产链路已经完成的基础上，为前台首页、事件详情页和后台审计页提供最小可用的只读产品接口层。

**Architecture:** 先建立稳定的 `ProductQueryService` 和 Pydantic 响应契约，再用 FastAPI 做很薄的 HTTP 适配层。接口层只读已有 PostgreSQL 数据，不触发采集、不触发 Agent、不修改核心生产表。

**Tech Stack:** Python 3.13, Pydantic 2.13.4, SQLAlchemy 2.0.41, FastAPI, Uvicorn, PostgreSQL, pytest 8.4.0。

---

## 1. 当前上下文

后端 P1 当前已经完成：

- P1-1 数据底座：新版核心表和服务层已经落地。
- P1-2 LangGraph 最小闭环：三 Agent stub workflow 已经跑通。
- P1-3 HN / GitHub 采集接入：公开来源可以写入 `source_signals`。
- P1-4 真实 LLM Agent：值班编辑、研究写作、审稿发布三个 LLM 节点已经可用。
- P1-5 发布质量：`revise/manual_review/reject`、slug 冲突、修订循环、agent run 审计和 PostgreSQL real provider smoke 已经完成。

当前仍沿用唯一新版主链路：

```text
SourceSignal
-> EventCandidate
-> EventDossier
-> ReviewResult
-> PublishedEvent
```

P1-6 的目标不是继续增强 Agent，也不是做前端页面，而是把已发布事件和后台审计数据以稳定契约暴露出来，让后续产品界面可以消费。

## 2. 关键决策

### 2.1 已确认方案

用户已确认采用 **方案 B：ProductQueryService + FastAPI 薄适配层**，分两步执行：

1. 先实现 `ProductQueryService` 和响应 schema，所有查询逻辑先在 Python 服务层测试通过。
2. 再引入 FastAPI，将 HTTP endpoint 做成很薄的一层，只负责参数解析、调用 query service、返回 JSON。

这样既不把 HTTP 框架提前绑死到业务查询里，也能满足产品接口层的实际消费需求。

### 2.2 备选方案

| 方案 | 内容 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- | --- |
| A | 只做 `ProductQueryService`，暂不做 HTTP | 最稳，依赖最少 | 前端还不能直接调用 | 不采用，仅作为内部第一步 |
| B | `ProductQueryService` + FastAPI 薄适配层 | 前端可直接消费，查询逻辑仍可测试复用 | 新增 `fastapi` / `uvicorn` 依赖，需要处理服务启动和联调 | 已确认采用 |
| C | Next.js route handler 直接查 PostgreSQL | 少一个 Python API 服务 | TypeScript 重写查询契约，容易和 worker 模型分叉 | 不推荐 |

本计划仍先实现 A 的服务层能力，再实现 B 的 HTTP 适配层。区别是：FastAPI 已进入 P1-6 范围，不再等待二次确认。

## 3. 阶段边界

### 3.1 本阶段负责

- 已发布事件列表查询。
- 已发布事件详情查询。
- pipeline run / agent run 审计查询。
- `manual_review` 队列查询。
- 查询响应 schema 和文档化字段契约。
- 只读接口测试、PostgreSQL smoke 和验收记录。

### 3.2 本阶段不负责

- 不开发前端页面。
- 不开发后台管理 UI。
- 不触发采集任务。
- 不触发 Agent / LangGraph workflow。
- 不提供发布、隐藏、驳回、重跑等写接口。
- 不实现权限系统、登录系统或线上部署。
- 不恢复 `EvidenceCard / EventCluster / ContentArtifact / QualityGateResult / Brief / BriefItem` 旧链路。
- 不把 API key、数据库密码或 `.env` 内容写入代码、文档或 git。

## 4. 接口设计草案

### 4.1 Public product endpoints

这些接口只面向产品前台读取已发布内容。

| Endpoint | 作用 | 数据来源 | 写库 |
| --- | --- | --- | --- |
| `GET /health` | 服务健康检查 | 应用进程，可选数据库 ping | 否 |
| `GET /events` | 首页事件卡片列表 | `published_events` | 否 |
| `GET /events/{slug}` | 事件详情页 | `published_events` + `event_dossiers` | 否 |

`GET /events` 默认只返回 `published_events.status = "published"` 的数据，排序建议：

```text
homepage_rank asc nulls last
ranking_score desc
published_at desc
created_at desc
```

### 4.2 Admin read-only endpoints

这些接口只用于后台审计和人工查看，不在 P1-6 提供写操作。

| Endpoint | 作用 | 数据来源 | 写库 |
| --- | --- | --- | --- |
| `GET /admin/pipeline-runs` | pipeline 运行列表 | `pipeline_runs` | 否 |
| `GET /admin/pipeline-runs/{run_id}` | 单次 pipeline 运行详情 | `pipeline_runs` | 否 |
| `GET /admin/pipeline-runs/{run_id}/agent-runs` | 某次运行的 Agent 记录 | `agent_runs` | 否 |
| `GET /admin/review-queue` | 人工审核队列 | `event_candidates` + `event_dossiers` + `review_results` | 否 |

`GET /admin/review-queue` 只返回当前仍处于 `manual_review` 的事件。若同一 candidate 存在多版 dossier / review，只返回最新 dossier 和最新 review，避免后台队列重复展示同一事件。

P1-6 不暴露 `agent_runs.trace_json.llm_raw_text` 的完整内容。若需要排查模型输出，只暴露：

- `duration_ms`
- `retry_count`
- `model_provider`
- `model_name`
- `prompt_version`
- `trace_json.token_usage`
- `status`
- `error_message`

完整 raw trace 仍保留在数据库里，后台 UI 是否展示留到后续权限设计阶段决定。

## 5. 响应契约草案

### 5.1 事件列表 item

```json
{
  "id": "pub_xxx",
  "slug": "hn-developers-debate-openai-coding-agents-2026-06-22",
  "title": "开发者社区讨论 OpenAI 式编码 Agent 对日常软件开发流程的影响",
  "card_summary": "用于首页卡片的一句话摘要。",
  "detail_summary": "用于详情页顶部的摘要。",
  "category": "模型与产品",
  "signal_label": "高热讨论",
  "cover_image_url": null,
  "homepage_rank": null,
  "published_at": "2026-06-22T12:00:00+00:00"
}
```

### 5.2 事件详情

```json
{
  "id": "pub_xxx",
  "slug": "hn-developers-debate-openai-coding-agents-2026-06-22",
  "title": "开发者社区讨论 OpenAI 式编码 Agent 对日常软件开发流程的影响",
  "detail_summary": "用于详情页顶部的摘要。",
  "detail_body": "面向用户阅读的详情正文。",
  "why_it_matters": "为什么这件事值得中文用户关注。",
  "follow_up_points": ["后续可以继续观察的问题"],
  "source_refs": [
    {
      "title": "HN discussion",
      "url": "https://news.ycombinator.com/item?id=..."
    }
  ],
  "category": "模型与产品",
  "signal_label": "高热讨论",
  "cover_image_url": null,
  "published_at": "2026-06-22T12:00:00+00:00"
}
```

说明：

- `cover_image_url` 当前可能为 `null`，因为 P1 后端尚未实现图片采集或图片生成。
- 前台事件列表不返回 `ranking_score`、`heat_score`、`importance_score` 等复杂分数；这些分数只用于内部排序和后台审计。
- `detail_body` 必须是读者口吻正文，不能出现候选事件、输入信号、来源边界、points、comments 等后台语言。
- 事件详情必须通过 `published_events.dossier_id` 联查发布时对应的 `event_dossiers` 版本，不能随意取该 candidate 的最新草稿版本。
- `source_refs` 是公开引用来源，不暴露内部 prompt 或完整 LLM trace。

### 5.3 Agent run 审计 item

```json
{
  "id": "arun_xxx",
  "pipeline_run_id": "run_xxx",
  "candidate_id": "cand_xxx",
  "dossier_id": "dos_xxx",
  "agent_name": "research_writer_llm",
  "agent_role": "writer",
  "model_provider": "openai",
  "model_name": "gpt-5.5",
  "prompt_version": "p1-4-writer-v1",
  "status": "succeeded",
  "duration_ms": 1234,
  "retry_count": 0,
  "token_usage": {
    "prompt_tokens": 1000,
    "completion_tokens": 500,
    "total_tokens": 1500
  },
  "error_message": null,
  "created_at": "2026-06-22T12:00:00+00:00"
}
```

## 6. 计划任务

### Task 0: 方案文档

**Files:**

- Create: `docs/05-实现计划/P1-6 产品接口层与最小API计划.md`
- Create: `docs/05-实现计划/P1-6 产品接口层与最小API计划.html`
- Modify: `docs/05-实现计划/README.md`
- Modify: `docs/README.md`
- Modify: `docs/00-项目总览/文档索引.md`
- Modify: `docs/00-项目总览/项目状态.md`

验收：

- 文档能说明本阶段做什么、不做什么。
- 文档能说明为什么先做 query service，再接 FastAPI。
- 文档能给出 endpoint、响应契约、测试策略和未覆盖范围。
- 当前 task 不改 `apps/worker` 代码。

### Task 1: ProductQueryService 和响应 schema

**Files:**

- Create: `apps/worker/worker/schemas/product.py`
- Create: `apps/worker/worker/services/product_query_service.py`
- Create: `apps/worker/tests/test_product_query_service.py`
- Modify: `apps/worker/worker/services/__init__.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-6 产品接口层与最小API计划.md`

测试先行：

```powershell
cd "C:\Users\admin\.config\superpowers\worktrees\AI World Radar\p1-data-foundation\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py -v
```

预期 RED：

```text
ModuleNotFoundError: No module named 'worker.services.product_query_service'
```

实现重点：

- `list_published_events(limit, offset, category)` 只返回 `status="published"`。
- `get_event_by_slug(slug)` 找不到时返回 `None`。
- `list_pipeline_runs(limit, offset)` 返回运行摘要。
- `get_pipeline_run(run_id)` 返回单次运行摘要。
- `list_agent_runs(run_id)` 默认隐藏 `llm_raw_text`，只暴露 token usage 摘要。
- `list_manual_review_items()` 返回等待人工审核的 candidate / dossier / review 摘要。
- 所有函数使用中文 docstring，说明输入和输出。

预期 GREEN：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py -v
```

执行记录（2026-06-22）：

- 已新增 `apps/worker/worker/schemas/product.py`，定义前台事件列表、事件详情、pipeline run、agent run 和人工审核队列响应契约。
- 已新增 `apps/worker/worker/services/product_query_service.py`，所有方法均为只读查询，不触发采集、Agent、workflow、发布或写库。
- 已新增 `apps/worker/tests/test_product_query_service.py`，覆盖 published 列表过滤和排序、slug 详情读取发布快照版本、agent run raw trace 隐藏、manual_review 队列只取最新 dossier/review。
- RED 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py -v`，真实失败为 `ModuleNotFoundError: No module named 'worker.services.product_query_service'`。
- GREEN 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py -v`，真实结果为 `4 passed in 0.70s`。
- 相关回归命令：`.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py tests/test_event_service.py tests/test_run_log_service.py -v`，真实结果为 `10 passed in 0.93s`。

### Task 2: FastAPI HTTP 薄适配层

**Files:**

- Modify: `apps/worker/pyproject.toml`
- Create: `apps/worker/worker/api/__init__.py`
- Create: `apps/worker/worker/api/app.py`
- Create: `apps/worker/worker/api/dependencies.py`
- Create: `apps/worker/tests/test_product_api.py`
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/05-实现计划/P1-6 产品接口层与最小API计划.md`

测试先行：

```powershell
cd "C:\Users\admin\.config\superpowers\worktrees\AI World Radar\p1-data-foundation\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_product_api.py -v
```

预期 RED：

```text
ModuleNotFoundError: No module named 'worker.api'
```

实现重点：

- 新增 `fastapi` 和 `uvicorn` 依赖。
- `create_app()` 只注册只读路由。
- endpoint 内只调用 `ProductQueryService`。
- 缺失事件详情返回 404。
- 不增加任何写接口。
- 管理端只读接口当前仅用于本地或内网开发；公开部署前必须补鉴权。

执行记录（2026-06-22）：

- 已新增 `apps/worker/tests/test_product_api.py`，覆盖 `GET /health`、`GET /events`、`GET /events/{slug}`、缺失 slug 404、pipeline run / agent run 审计查询和 `manual_review` 队列查询。
- 首次 RED 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_product_api.py -v`，真实失败为 `ModuleNotFoundError: No module named 'fastapi'`。
- 已用 `pip index versions fastapi` / `pip index versions uvicorn` 查询本机可用版本，当前分别为 `fastapi 0.138.0`、`uvicorn 0.49.0`。
- 已修改 `apps/worker/pyproject.toml`，新增 `fastapi==0.138.0`、`uvicorn==0.49.0`，并执行 `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`，真实输出包含 `Successfully installed ... fastapi-0.138.0 ... uvicorn-0.49.0`。
- 第二次 RED 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_product_api.py -v`，真实失败为 `ModuleNotFoundError: No module named 'worker.api'`。
- 已新增 `apps/worker/worker/api/__init__.py`、`apps/worker/worker/api/dependencies.py`、`apps/worker/worker/api/app.py`。
- GREEN 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_product_api.py -v`，真实结果为 `2 passed in 1.05s`。
- 联合回归命令：`.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py tests/test_product_api.py -v`，真实结果为 `6 passed in 1.13s`。

### Task 3: PostgreSQL 只读 smoke 和文档验收

**Files:**

- Modify: `docs/07-验收与运行/后端P1测试记录.md`
- Modify: `docs/00-项目总览/项目状态.md`

验证命令：

```powershell
cd "C:\Users\admin\.config\superpowers\worktrees\AI World Radar\p1-data-foundation\apps\worker"
.\.venv\Scripts\python.exe -m pytest -v
```

如果 Task 2 已实现，还需要运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_product_api.py -v
```

PostgreSQL smoke 只做读取，不触发 Agent：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_product_queries.py --database-url "<本机 ai_world_radar 连接串>"
```

执行记录（2026-06-22）：

- 已新增 `apps/worker/scripts/smoke_product_queries.py`，使用 `create_worker_engine` 和 `autoflush=False` session，只调用 `ProductQueryService` 做只读查询，不触发采集、Agent、workflow、发布或写库。
- 已新增 `apps/worker/tests/test_smoke_product_queries_script.py`，测试数据使用临时 SQLite，写入 1 条 published event、1 条 pipeline run、1 条 agent run 和 1 条 manual_review 事件后执行脚本读取。
- RED 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_smoke_product_queries_script.py -v`，真实失败为 `can't open file ... scripts\smoke_product_queries.py: [Errno 2] No such file or directory`。
- GREEN 命令：`.\.venv\Scripts\python.exe -m pytest tests/test_smoke_product_queries_script.py -v`，真实结果为 `1 passed in 1.91s`。
- P1-6 联合回归命令：`.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py tests/test_product_api.py tests/test_smoke_product_queries_script.py -v`，真实结果为 `7 passed in 2.88s`。
- worker 全量回归命令：`.\.venv\Scripts\python.exe -m pytest -v`，最新真实结果为 `96 passed in 23.40s`。
- PostgreSQL 只读 smoke 命令：`.\.venv\Scripts\python.exe scripts\smoke_product_queries.py --database-url postgresql+psycopg://postgres:<password>@localhost:5432/ai_world_radar`，真实 stdout 为 `status=succeeded`、`events_count=3`、`detail_found=true`、`pipeline_runs_count=3`、`agent_runs_count=7`、`review_queue_count=0`、`first_event_slug=demo-openai-releases-a-new-developer-tool`、`first_pipeline_run_id=run_9edd05cbf4aa464593172c01911fa068`。
- PostgreSQL 核心表只读计数查询真实输出：`sources_count=2`、`source_signals_count=3`、`source_signal_counts_by_source={"demo":1,"hn_algolia":2}`、`event_candidates_count=3`、`event_candidate_signals_count=3`、`event_dossiers_count=6`、`review_results_count=6`、`published_events_count=3`、`pipeline_runs_count=3`、`agent_runs_count=15`。
- 真实 HTTP 运行验收（2026-06-23）：启动 `uvicorn worker.api.app:create_app --factory --host 127.0.0.1 --port 8016` 连接本机 PostgreSQL `ai_world_radar`，逐个请求 `/health`、`/events`、`/events/{slug}`、`/admin/pipeline-runs`、`/admin/pipeline-runs/{run_id}`、`/admin/pipeline-runs/{run_id}/agent-runs`、`/admin/review-queue` 均通过。真实 HN 事件详情 `hn-developers-debate-openai-coding-agents-2026-06-22` 返回 `status_code=200`、正文长度 `1359`、`source_refs_count=1`、`follow_up_points_count=4`。验收结束后已停止 uvicorn。

## 7. 验收标准

P1-6 完成后至少满足：

- 默认不会触发采集、Agent 或发布。
- 已发布事件列表只返回 `published_events.status = "published"`。
- 事件详情按 `slug` 查询，缺失时有明确 not found 行为。
- 后台审计接口能查看 pipeline run 和 agent run 摘要。
- agent run 默认不暴露完整 `llm_raw_text`。
- `manual_review` 队列可查询。
- worker 全量 pytest 通过。
- PostgreSQL `ai_world_radar` 上可读取之前 real provider smoke 生成的发布事件。
- 文档记录真实命令、真实输出、失败修复、未覆盖范围和是否可以进入前端页面开发。

## 8. 未覆盖范围

- API 鉴权和管理员权限。
- 写接口和人工修正动作。
- 前端页面。
- 图片采集、图片生成和封面图质量。
- 线上部署、日志采集、监控告警。
- 大规模分页性能、索引优化和缓存。

## 9. 当前执行结论

P1-6 后端产品接口层已完成最小闭环：查询服务、响应 schema、FastAPI 只读 HTTP endpoint、脚本化 PostgreSQL 只读 smoke、真实 HTTP 运行验收和验收文档均已落地。当前可以进入产品页面联调或前端页面开发，但公开部署前仍必须补 API 鉴权和管理员权限。

后续继续守住三条边界：

- FastAPI 只做只读产品接口，不触发采集、Agent、发布或重跑。
- 业务查询规则放在 `ProductQueryService`，HTTP endpoint 不写复杂业务逻辑。
- 管理端接口当前只服务本地开发和后台页面联调，公开部署前必须补鉴权。
