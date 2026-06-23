# 实现计划

本目录用于存放 AI World Radar 各阶段实现计划。

当前已有计划文档：

- `后端P1实现计划与功能切片拆解.md`
- `后端P1实现计划与功能切片拆解.html`
- `P1实施路线图与第一阶段后端数据底座计划.md`
- `P1实施路线图与第一阶段后端数据底座计划.html`
- `P1-2 LangGraph工作流与三Agent最小闭环计划.md`
- `P1-2 LangGraph工作流与三Agent最小闭环计划.html`
- `P1-3 HN与GitHub采集接入新版链路计划.md`
- `P1-3 HN与GitHub采集接入新版链路计划.html`
- `P1-4 真实LLM Agent节点替换计划.md`
- `P1-4 真实LLM Agent节点替换计划.html`
- `P1-6 产品接口层与最小API计划.md`
- `P1-6 产品接口层与最小API计划.html`
- `P1-7 GitHub热门项目与官网源扩展计划.md`
- `P1-7 GitHub热门项目与官网源扩展计划.html`
- `P1-8 官方与开发者平台公开源扩展计划.md`
- `P1-8 官方与开发者平台公开源扩展计划.html`

`后端P1实现计划与功能切片拆解` 定义旧版后端 P1 第一条纵向功能切片：HN AI 事件生产闭环。该文档保留为历史参考。

`P1实施路线图与第一阶段后端数据底座计划` 是新版 PRD v2.0、Agent 系统设计 v1.0、技术架构与数据模型设计 v1.0 之后的 P1-1 实施依据，定义 P1 总路线图和第一阶段后端数据底座重构任务。P1-1 已完成，保留为数据底座验收依据。

`P1-2 LangGraph工作流与三Agent最小闭环计划` 是 P1-1 数据底座完成后的 P1-2 实施依据和完成记录，定义 LangGraph 工作流、三 Agent 确定性 stub、工程 tool 适配层、新版脚本入口、旧可执行代码物理清理和验收记录要求。P1-2 已完成。

`P1-3 HN与GitHub采集接入新版链路计划` 是 P1-2 最小闭环完成后的 P1-3 实施依据和完成记录，定义 HN / GitHub 真实采集如何映射并写入新版 `source_signals`，以及如何复用 `scripts/run_event_pipeline.py` 消费已入库信号产出 `PublishedEvent`。P1-3 已完成。

`P1-4 真实LLM Agent节点替换计划` 是 P1-3 采集接入完成后的 P1-4 实施依据和完成记录，定义如何在不改变新版主链路的前提下，把值班编辑、研究写作、审稿发布三个确定性 stub 逐个替换为真实 LLM Agent。P1-4 已完成，fake LLM smoke 输出 `status=succeeded`、`published_count=1`、`agent_runs_count=3`；本机 OpenAI / OpenAI-compatible SDK smoke 已通过。2026-06-22 已补高热度 HN 来源 real provider publish smoke，输出 `status=succeeded`、`published_count=1`，reviewer 判断 `publish/low`，并在 `checked_items` 中确认该来源支撑“社区正在热议”而不是“官方已确认事实”。同日已补齐详情正文信息密度和读者口吻兜底。

P1-5 发布质量与工程准备第一轮已完成：已补齐 `revise/manual_review/reject` 非发布分支、slug 冲突和幂等发布、LangGraph 修订循环深度、agent run 耗时和 token usage 审计；本机 PostgreSQL `ai_world_radar` 高热度 HN real provider smoke 已通过，`run_id=run_9edd05cbf4aa464593172c01911fa068`、`published_count=1`、`agent_runs_count=7`。最新 worker 全量复验为 `89 passed in 19.66s`。

`P1-6 产品接口层与最小API计划` 是后端 P1 进入产品接口层前的方案文档，定义只读产品查询边界、`ProductQueryService` 优先的实现顺序、FastAPI 薄适配层、事件列表 / 详情 / 后台审计接口草案、响应契约和验收标准。当前状态为用户已确认采用“ProductQueryService + FastAPI 薄适配层”方案，下一步进入测试先行实现。

`P1-7 GitHub热门项目与官网源扩展计划` 是 P1-6 产品接口层和真实链路验收后的 source 扩展实施依据与完成记录，定义 GitHub repo momentum / star 增长源、官网 RSS/Atom/轻量 HTML 官方源、采集脚本扩展、测试策略、smoke 和文档验收要求。P1-7 已完成：`github_repo_trends`、`official_feeds` / `official_news` 均已接入 `collect_source_signals.py`，最终 worker 全量测试为 `108 passed in 26.23s`，fresh SQLite smoke 和本机 PostgreSQL live source smoke 均通过。

`P1-8 官方与开发者平台公开源扩展计划` 是 P1-7 后继续扩展低成本公开平台源的实施依据，优先选择 RSS / Atom / XML feed，首批候选包括 OpenAI News、GitHub Changelog、Hugging Face Blog、Google AI Blog、AWS Machine Learning Blog、PyTorch Blog 和 Ollama Blog。P1-8 启动基线为 `108 passed in 31.45s`。
