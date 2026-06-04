# AI World Radar Agent 系统设计

版本：v0.2

更新时间：2026-06-04

阶段：P1 Agent 系统设计修订版

## 1. 文档目的

本文档用于定义 AI World Radar P1 的 Agent 系统设计 v0.2。它描述 Agent 在后端情报生产链路中的职责、边界、工具调用方式、LangGraph 工作流设计，以及与工程代码、LLMClient、数据库发布链路之间的关系。

本文档不讨论：

- UI 视觉设计。
- 具体前端页面。
- 具体数据库字段细节。
- 部署方案。
- P2 AI 追问助手。

本文档的核心问题是：

> P1 的 Agent 到底是什么，哪些事情由 Agent 做，哪些事情必须由工程代码控制。

## 2. v0.2 修订背景

v0.1 文档形成于早期 Agent 架构讨论阶段。后续产品和技术设计继续推进，已经确认了新的 P1 口径：

- P1 不单独建 `RawItem` 表。
- P1 不单独建 `CandidateEvent` 表。
- P1 不做真实性核验。
- P1 使用 LangGraph / LangChain。
- P1 迁入用户已有 Python LLMClient。
- P1 复杂节点允许受控 tool-calling。
- P1 后端第一功能切片是 HN AI 事件生产闭环。

因此需要将 Agent 系统设计升级为 v0.2，避免旧文档中的 Raw Item、Candidate Router、可信度和待核验等旧口径误导后续开发代理。

## 3. Agent 系统的核心定位

AI World Radar 的 Agent 不是自由浏览互联网的万能 Agent，而是：

> 工程化情报流水线中的多阶段 Agent Workflow。

一句话定义：

> 工程代码负责稳定执行，Agent 负责语义判断和内容生产。

具体来说：

```text
工程代码负责：
采集、解析、存储、调度、发布、失败控制。

Agent 负责：
理解、聚合、排序、写作、简报、质量门禁。
```

AI World Radar 的目标不是做普通 AI 新闻聚合站，也不是做一个把网页丢给大模型总结的工具，而是为中文 AI 学习型用户提供全球 AI 圈事件情报雷达。

## 4. P1 Agent 边界

P1 的 Agent 可以调用工具，但必须受控。

P1 Agent 允许：

- 在指定节点调用白名单工具。
- 使用来源内容和数据库已有证据。
- 生成结构化结果。
- 参与事件聚合、内容生成和质量门禁。

P1 Agent 不允许：

- 自由浏览全网。
- 自由决定发布。
- 直接修改核心数据库状态。
- 绕过工程代码采集来源。
- 无限循环调用工具。
- 绕过质量门禁。

核心边界是：

> Agent 可以提出判断和生成内容，但主流程、数据库写入和发布状态由工程代码控制。

## 5. P1 不做什么

P1 Agent 系统不做：

- 不做自由自治 Agent。
- 不做复杂研究 Agent。
- 不做 AI 追问助手。
- 不做真实性核验。
- 不做用户个性化推荐。
- 不做 embedding 聚合。
- 不做 X、Reddit、YouTube 复杂高热平台采集。
- 不做 `RawItem` 独立表。
- 不做 `CandidateEvent` 独立表。

这些内容后续可进入 P1.5 或 P2。

## 6. 总体架构：工程流水线 + LangGraph Agent Workflow

P1 采用：

```text
工程代码控制主流程
LangGraph 编排 Agent 工作流
LangChain 支持模型与工具能力
LLMClient 提供底层 chat / stream / provider 切换
```

总体链路：

```text
Source Adapter
-> SourceItem
-> LangGraph Workflow
   -> EvidenceAgent
   -> EventClusterAgent
   -> RankingAgent
   -> DetailWriterAgent
   -> BriefWriterAgent
   -> QualityGateAgent
-> PublishService
-> PostgreSQL
```

其中：

- Source Adapter 是工程代码。
- LangGraph Workflow 是 Agent 编排层。
- Agent 节点负责语义判断和内容生成。
- PublishService 是工程代码。
- PostgreSQL 是系统事实记录。

## 7. 工程代码负责的部分

工程代码负责确定性、可复现、可调试的部分：

- 信息源配置。
- HN / GitHub Changelog 采集。
- URL 归一化。
- 基础字段解析。
- PostgreSQL 读写。
- PipelineRun 记录。
- 发布状态写入。
- 失败状态记录。
- Agent 最大步数限制。
- 工具白名单控制。
- 运行脚本入口。

工程代码不把核心控制权交给 Agent。

## 8. Agent 负责的部分

Agent 负责语义性、生成性、判断性的部分：

- 判断内容是否与 AI 圈相关。
- 提取 EvidenceCard。
- 判断多个 EvidenceCard 是否属于同一事件。
- 解释事件热度和中文用户价值。
- 生成事件卡片内容。
- 生成事件详情内容。
- 生成今日简报内容。
- 检查内容是否跑题、空泛、夸大、缺来源。

Agent 的结果必须经过：

- 结构化解析。
- 质量门禁。
- 工程代码发布。

Agent 不是数据库发布者，而是情报生产链路中的语义处理者。

## 9. LLMClient 的职责边界

用户已有 Python LLMClient 会迁入项目，但它不是 Agent 系统本身。

LLMClient 只负责：

- provider 切换。
- model 切换。
- api_key / base_url 配置。
- chat。
- stream_chat。
- 基础 OpenAI-compatible 调用。

LLMClient 不负责：

- 业务 prompt。
- EvidenceCard schema。
- Brief schema。
- 工具绑定。
- Agent 循环。
- 质量门禁。
- 数据库写入。

一句话：

> LLMClient 是模型调用底座，不是业务 Agent。

结构化输出、工具绑定和多步 Agent 行为应放在具体 Agent 节点中设计。

## 10. LangGraph 工作流设计

P1 LangGraph 主流程暂定为：

```text
collect_sources
-> build_evidence_cards
-> cluster_events
-> rank_events
-> generate_event_content
-> generate_brief
-> quality_gate
-> publish_results
```

节点分类：

```text
工程节点：
collect_sources
publish_results

Agent 节点：
build_evidence_cards
cluster_events
rank_events
generate_event_content
generate_brief
quality_gate
```

第一版工作流不追求复杂分支，先追求：

- 状态清晰。
- 输入输出明确。
- 失败可记录。
- 节点可单独测试。
- 可通过本地命令手动触发。

## 11. Agent 节点设计

P1 Agent 节点分成 6 个：

```text
EvidenceAgent
EventClusterAgent
RankingAgent
DetailWriterAgent
BriefWriterAgent
QualityGateAgent
```

### 11.1 EvidenceAgent

EvidenceAgent 从 SourceItem 生成 EvidenceCard。

职责：

- 判断是否 AI 相关。
- 提取主体。
- 提取事件触发点。
- 提取分类建议。
- 提取热度线索。
- 提取重要度线索。
- 给出中文用户价值理由。

### 11.2 EventClusterAgent

EventClusterAgent 判断多个 EvidenceCard 是否属于同一事件。

职责：

- 判断相似来源是否应该合并。
- 输出合并原因。
- 输出不合并原因。
- 生成事件聚合结果。

第一版使用：

```text
规则合并 + Agent 辅助判断
```

不使用 embedding。

### 11.3 RankingAgent

RankingAgent 根据热度、重要度、中文用户价值给事件排序。

排序口径：

```text
热度主导 + 重要度兜底 + 中文用户价值修正
```

输出：

- ranking_score。
- ranking_reason。
- 是否适合发布。
- 是否适合进入今日简报。

### 11.4 DetailWriterAgent

DetailWriterAgent 负责生成事件详情正文。

它可以调用受控工具补充上下文，但不能自由浏览全网。

输出：

- 事件标题。
- 事件摘要。
- 详情正文。
- 关键背景。
- 为什么值得关注。
- 来源引用。
- 后续关注点。

### 11.5 BriefWriterAgent

BriefWriterAgent 负责从已发布事件中生成今日简报。

规则：

- 简报不是全量事件合集。
- 简报只选 Top 3-5 个重点事件。
- 简报应让用户只看它也能知道今日重点。
- 每条 brief item 必须能关联到 PublishedEvent。

### 11.6 QualityGateAgent

QualityGateAgent 检查生成内容质量。

它不做真实性核验，只做生成质量和工程发布安全检查。

输出建议：

```text
publish
regenerate
manual_review
discard
```

## 12. 受控 Tool-Calling 设计

P1 支持 tool-calling，但只在复杂节点中使用。

允许使用工具的节点：

```text
EvidenceAgent
DetailWriterAgent
BriefWriterAgent
QualityGateAgent
```

第一版工具白名单：

```text
fetch_url_content(url)
fetch_hn_comments(item_id)
extract_page_metadata(url)
search_existing_evidence(query)
load_cluster_evidence(cluster_id)
```

工具使用限制：

- 每个 Agent 最多 3-5 步。
- 每个 Agent 最多 2-3 次工具调用。
- 工具只能读数据，不能直接发布。
- 工具不能绕过来源策略自由爬全网。
- 工具调用结果必须进入 Agent 输入上下文。

这样既保留 Agent 性，又保持工程可控。

## 13. EvidenceCard 设计口径

P1 不再把 RawItem 作为正式 P1 表。

EvidenceCard 是：

> 来源信号 + AI 理解结果的统一内部证据单元。

EvidenceCard 应同时保存来源信息和 AI 理解结果。

来源信息包括：

- original_title。
- original_url。
- source_id。
- published_at。
- raw_summary / raw_excerpt。
- raw_heat_metrics。

AI 理解结果包括：

- claim_summary。
- normalized_title。
- subjects。
- event_trigger。
- event_type。
- category。
- heat_clues。
- impact_clues。
- audience_value_reason。
- candidate_score。
- merge_key_hint。

EvidenceCard 不是用户看到的事件卡，而是 Agent 后续聚合和写作的证据材料。

## 14. EventCluster 设计口径

EventCluster 是多个 EvidenceCard 聚合后的内部事件。

它解决的问题是：

- 多条来源信号是不是在讲同一件事。
- 这个事件的核心主体是什么。
- 事件触发点是什么。
- 应该如何排序和发布。

EventCluster 不等于 PublishedEvent。

```text
EventCluster：内部事件
PublishedEvent：公开展示事件
```

第一版聚合策略：

```text
规则合并 + Agent 辅助判断
不使用 embedding
```

聚合依据：

- 主体相同。
- 触发点相似。
- 标题相似。
- URL / canonical URL 相同。
- 发布时间窗口接近。
- Agent 判断为同一事件。

## 15. 内容生成 Agent 设计

内容生成不再是简单摘要，而是事件内容生产。

DetailWriterAgent 的输入包括：

- EventCluster。
- 关联 EvidenceCards。
- RankingReason。
- 来源链接。
- 可选工具补充结果。

输出包括：

- 事件标题。
- 事件摘要。
- 详情正文。
- 关键背景。
- 为什么值得关注。
- 来源引用。
- 后续关注点。

要求：

- 不能直接搬运原文。
- 不能把热议写成事实。
- 不能夸大影响。
- 中文表达要自然。
- 用户阅读时不应看到大量结构化字段堆叠。

第一版详情内容先以“可读正文”为目标，不追求深度长文。

## 16. Brief 生成 Agent 设计

BriefWriterAgent 负责从已发布事件中生成今日简报内容。

输入：

- Top PublishedEvents。
- 对应 card / detail 内容。
- RankingReason。
- 来源信息。

输出：

- brief title。
- brief summary。
- brief items。
- 每条 brief item 对应 published_event_id。

规则：

- 简报不是全量事件合集。
- 简报只选 Top 3-5 个重点事件。
- 简报应让用户只看它也能知道今日重点。
- 每条 brief item 必须能跳到事件详情。

第一版 brief 生成可以先服务后端数据验收，不先考虑页面排版。

## 17. Quality Gate Agent 设计

P1 Quality Gate 不做真实性核验。

它只检查生成质量和工程发布安全：

- 内容是否为空。
- 结构是否可解析。
- 标题和正文是否明显不一致。
- 是否缺少来源链接。
- 是否直接搬运原文。
- 是否过度夸张。
- 是否把不确定内容写成确定事实。
- event_card 和 event_detail 是否成对存在。
- brief_item 是否关联 published_event。

输出建议：

```text
publish
regenerate
manual_review
discard
```

注意：

> manual_review 不是事实核验状态，只说明当前内容不适合自动发布。

## 18. 发布与入库边界

Agent 不能直接发布。

Agent 输出的是结构化建议和内容草稿，最终由工程服务写入数据库。

发布由：

```text
PublishService
```

负责。

写入内容包括：

- published_events。
- content_artifacts。
- briefs。
- brief_items。
- quality_gate_results。
- pipeline_runs。

核心边界：

```text
Agent 生成内容
QualityGate 给建议
PublishService 决定写入发布表
```

如果质量门禁失败：

- 不写入 published 状态。
- 可写入 draft / manual_review / discarded 状态。

## 19. 后端 P1 第一功能切片：HN AI 事件生产闭环

后端 P1 的第一交付切片不是“采集模块”，而是：

> HN AI 事件生产闭环。

完整链路：

```text
Hacker News API
-> SourceItem
-> EvidenceAgent
-> EventClusterAgent
-> RankingAgent
-> DetailWriterAgent
-> BriefWriterAgent
-> QualityGateAgent
-> PublishService
-> PostgreSQL
-> PipelineRun 报告
```

完成后应能通过本地命令触发：

```powershell
python -m app.scripts.run_pipeline --source hn --limit 20
```

并在数据库中得到：

- EvidenceCard。
- EventCluster。
- ContentArtifact。
- PublishedEvent。
- Brief。
- BriefItem。
- QualityGateResult。
- PipelineRun。

这一节的关键口径是：

> 模块是实现单元，功能切片是交付单元。

## 20. P1、P1.5 与 P2 演进

### 20.1 P1

P1 包括：

- HN。
- GitHub Changelog。
- LangGraph Agent Workflow。
- 受控 tool-calling。
- PostgreSQL 入库。
- 本机手动命令触发。
- 不做真实性核验。
- 不做复杂高热平台。

### 20.2 P1.5

P1.5 可增强：

- Reddit。
- YouTube。
- GitHub Trending。
- Hugging Face Trending。
- embedding 聚合。
- 更强热度信号。
- 更强失败兜底。
- 可选 Docker Compose。

### 20.3 P2

P2 可考虑：

- 事件级 AI 追问助手。
- 用户收藏。
- 订阅提醒。
- 个性化。
- 趋势专题。
- 更完整管理后台。

## 21. 与旧版 v0.1 的差异

| 主题 | v0.1 | v0.2 |
| --- | --- | --- |
| Raw Item Store | P1 模块 | 不作为正式 P1 表，改为临时 SourceItem |
| Candidate Router Agent | 独立 Agent | 合并进 EvidenceAgent / RankingAgent / PublishService |
| 真实性 / 可信度 | 有事实型、待核验、可信度权重 | P1 不做真实性核验，只做生成质量门禁 |
| 写作 Agent 读取材料 | 不能读取网页 | 不能自由浏览，但可调用白名单工具补充上下文 |
| Agent 框架 | 抽象 Agent 流水线 | 明确使用 LangGraph / LangChain |
| LLMClient | 未明确 | 只作为底层模型调用底座 |
| 开发切片 | 未定义 | 后端 P1 第一切片为 HN AI 事件生产闭环 |

## 22. 下一步

新版 Agent 系统设计确认后，下一步进入：

> 后端 P1 实现计划与功能切片拆解。

在写后端实现计划前，后续代理必须先阅读：

1. `docs\项目状态.md`
2. `docs\Agent系统设计.md`
3. `docs\技术架构与数据模型设计.md`

然后才能开始底座落地和 HN 功能切片开发。
