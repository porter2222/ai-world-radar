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

`后端P1实现计划与功能切片拆解` 定义旧版后端 P1 第一条纵向功能切片：HN AI 事件生产闭环。该文档保留为历史参考。

`P1实施路线图与第一阶段后端数据底座计划` 是新版 PRD v2.0、Agent 系统设计 v1.0、技术架构与数据模型设计 v1.0 之后的 P1-1 实施依据，定义 P1 总路线图和第一阶段后端数据底座重构任务。P1-1 已完成，保留为数据底座验收依据。

`P1-2 LangGraph工作流与三Agent最小闭环计划` 是 P1-1 数据底座完成后的 P1-2 实施依据和完成记录，定义 LangGraph 工作流、三 Agent 确定性 stub、工程 tool 适配层、新版脚本入口、旧可执行代码物理清理和验收记录要求。P1-2 已完成。

`P1-3 HN与GitHub采集接入新版链路计划` 是 P1-2 最小闭环完成后的 P1-3 实施依据和完成记录，定义 HN / GitHub 真实采集如何映射并写入新版 `source_signals`，以及如何复用 `scripts/run_event_pipeline.py` 消费已入库信号产出 `PublishedEvent`。P1-3 已完成。

`P1-4 真实LLM Agent节点替换计划` 是 P1-3 采集接入完成后的 P1-4 实施依据和完成记录，定义如何在不改变新版主链路的前提下，把值班编辑、研究写作、审稿发布三个确定性 stub 逐个替换为真实 LLM Agent。P1-4 已完成，最新 worker 全量 pytest 为 `69 passed in 16.63s`，fake LLM smoke 输出 `status=succeeded`、`published_count=1`、`agent_runs_count=3`；本机 OpenAI / OpenAI-compatible SDK smoke 已通过，真实 provider pipeline 已跑到三类 LLM Agent，但内置示例来源被 reviewer 判为 `manual_review`，未自动发布。
