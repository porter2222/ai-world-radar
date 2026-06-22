# AI World Radar 文档入口

本文档是 AI World Radar 项目的文档导航入口。新对话、新代理或开发者进入项目时，应先从这里开始。

## 推荐阅读顺序

1. `00-项目总览/项目状态.md`
2. `00-项目总览/文档索引.md`
3. `01-产品定义/产品宪章.md`
4. `01-产品定义/产品需求文档.md`
5. `02-信息源策略/信息源策略.md`
6. `04-系统设计/Agent系统设计.md`
7. `04-系统设计/技术架构与数据模型设计.md`
8. `05-实现计划/P1实施路线图与第一阶段后端数据底座计划.md`
9. `05-实现计划/P1-2 LangGraph工作流与三Agent最小闭环计划.md`
10. `05-实现计划/P1-3 HN与GitHub采集接入新版链路计划.md`
11. `05-实现计划/P1-4 真实LLM Agent节点替换计划.md`
12. `05-实现计划/P1-6 产品接口层与最小API计划.md`
13. `05-实现计划/后端P1实现计划与功能切片拆解.md`
14. `06-代理任务书/后端P1开发代理任务书.md`
15. `07-验收与运行/后端P1测试记录.md`

## 目录说明

```text
00-项目总览
  项目状态、文档索引、跨对话交接信息。

01-产品定义
  产品宪章、PRD 等产品层文档。

02-信息源策略
  P1 冷启动信息源策略。

03-调研资料
  GitHub 采集策略、首页事件卡片、QFT 参考项目等调研资料。

04-系统设计
  Agent 系统设计、技术架构、数据模型。

05-实现计划
  后端 P1、前端 P1、部署等实现计划。

06-代理任务书
  后端代理、Agent 代理、前端代理、运维代理、验收代理任务书。

07-验收与运行
  本地启动说明、验收清单、运行记录。
```

## 当前阶段

当前项目已完成产品宪章、新版 PRD v2.0、首页事件卡片字段调研、信息源策略、新版 Agent 系统设计 v1.0、新版技术架构与数据模型设计 v1.0、后端 P1 第一轮工程骨架实现、P1-1 后端数据底座重构、P1-2 LangGraph 工作流与三 Agent 最小闭环、P1-3 HN / GitHub 采集接入新版链路、P1-4 真实 LLM Agent 节点替换，以及 P1-5 发布质量与工程准备第一轮闭环。P1-5 已补齐 `revise/manual_review/reject` 非发布分支、slug 冲突和幂等发布、LangGraph 修订循环深度、agent run 耗时和 token usage 审计；本机 PostgreSQL `ai_world_radar` 高热度 HN real provider smoke 已通过，`run_id=run_9edd05cbf4aa464593172c01911fa068`、`published_count=1`、`agent_runs_count=7`。最新 worker 全量复验为 `89 passed in 19.66s`。P1-6 产品接口层已确认直接采用 `ProductQueryService + FastAPI` 薄适配层方案，下一步进入测试先行实现。

后端 P1 发布前验收清单已新增：`docs/07-验收与运行/后端P1发布前验收清单.md`。当前结论为本地有条件通过；远程 push 当前因本机无法连接 `github.com:443` 阻塞，网络恢复后需要重试。

最新产品基线已经调整为：

> P1 以“事件档案生产与发布”为核心；晨报后置到 P1.5，基于已发布事件生成。

新版 Agent 系统设计 v1.0 已确认编辑部式 Multi-Agent 终局蓝图和 P1 阶段化落地口径。新版技术架构与数据模型设计 v1.0 已更新为 `Next.js + FastAPI Product API + Python Worker + PostgreSQL` 的 P1-6 落地架构：Next.js 负责界面，FastAPI 提供只读产品接口，Python Worker 负责后台生产链路。

下一步建议进入：

> 进入产品接口层 P1-6 Task 1，优先做 `ProductQueryService`、响应 schema、事件列表、事件详情、pipeline run / agent run 审计查询和 `manual_review` 队列查询；随后实现 FastAPI 薄适配层。默认 `AGENT_MODE=stub` 不变，真实 LLM 调用继续显式开启；FastAPI 当前只做只读接口，不触发采集、Agent、发布或重跑。
