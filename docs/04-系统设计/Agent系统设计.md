# AI World Radar Agent 系统设计

版本：v1.0

更新时间：2026-06-12

阶段：终局架构蓝图与阶段化落地口径

适用范围：AI World Radar 事件档案生产与发布系统

## 1. 文档目的

本文档用于定义 AI World Radar 的新版 Agent 系统设计。它描述终局形态下系统如何使用编辑部式 Multi-Agent 工作流，把全球 AI 圈的碎片化公开信号加工成中文用户能理解、可追踪、可修正的事件档案。

本文档同时明确 P1 的落地边界：终局蓝图可以完整成熟，但第一阶段实现必须克制，先完成单机可运行的事件生产闭环，再逐步引入队列、缓存、对象存储、向量检索、成本监控等增强能力。

本文档不展开具体 UI 视觉设计、前端组件细节、部署方案、完整字段类型和具体代码实现。数据库对象会在本文中定义概念模型，后续需要在技术架构与数据模型设计文档中进一步细化为迁移脚本和字段约束。

## 2. 核心结论

AI World Radar 的 Agent 系统不是自由上网写新闻的万能 Agent，也不是普通爬虫后面接一个摘要 prompt。

它的核心定位是：

> 基于 LangGraph 的编辑部式 Multi-Agent 情报生产系统。

更具体地说：

> 工程系统负责稳定采集、存储、状态流转、发布和审计；Agent 负责事件判断、资料理解、中文写作、审稿修订和发布建议。

终局架构采用：

```text
LangGraph 工作流编排
+ 编辑部式主 Agent
+ 能力型子 Agent / Skill
+ 工程 Tool 白名单
+ PostgreSQL 状态与审计记录
+ 后台监控与人工修正
```

P1 实现采用：

```text
单机 Python Worker
+ PostgreSQL
+ 本地文件缓存
+ 同步 pipeline
+ 最小 Agent 闭环
+ 最小运行记录
```

## 3. 业务生产流程

P1 的核心产物不是简报，也不是新闻列表，而是事件档案。

端到端业务流程为：

```text
外部信号
-> 标准化信号
-> 判断哪些值得关注
-> 把重复信号合并成同一事件
-> 给事件排序
-> 整理事件资料
-> 写成中文事件档案
-> 审稿检查
-> 发布到前台
-> 后台可监控、可修改、可隐藏
```

也可以概括为：

```text
收集线索
-> 发现事件
-> 理解事件
-> 写成内容
-> 检查质量
-> 发布展示
-> 后台修正
```

外部信号可以来自 Hacker News、GitHub、Hugging Face、公司官网、AI 新闻站、中文聚合站，以及后续扩展的 X、Reddit、YouTube 等平台。

信号刚进入系统时不能直接展示给用户。它们可能重复、零散、英文、上下文不足、标题党，或者只是讨论热度，不一定构成一个值得展示的事件。系统要把这些信号加工成用户能看懂的事件档案。

## 4. 职责边界

系统必须先区分工程动作和智能判断。

工程代码负责确定性动作：

- 采集外部信息。
- 解析标题、链接、时间、来源和热度指标。
- 正文抓取和本地缓存。
- URL 归一化和 source hash 计算。
- PostgreSQL 读写。
- 状态流转。
- 发布写库。
- 最大重试次数控制。
- 运行日志和后台记录。
- 幂等控制。

Agent 负责语义判断和内容生产：

- 判断内容是否 AI 相关。
- 判断多个信号是否指向同一事件。
- 判断事件是否值得展示。
- 判断事件对中文用户的价值。
- 整理来源材料。
- 生成事件标题、首页卡和详情正文。
- 检查内容是否空泛、夸大、搬运或来源不足。
- 根据审稿意见修订内容。

核心原则：

> Agent 可以提出判断、草稿和建议，但不能直接修改核心状态，不能直接发布，不能绕过工程服务。

## 5. 总体架构

新版系统采用五层架构：

```text
1. Source Layer 信息源层
2. Workflow Layer 工作流编排层
3. Agent Layer 编辑部 Agent 层
4. Tool / Skill Layer 能力层
5. Product Service Layer 产品服务层
```

整体链路：

```text
Source Adapter
-> Source Signal
-> LangGraph Workflow
   -> On-duty Editor Agent
   -> Research Writer Agent
   -> Review Publisher Agent
-> Publish Service
-> PostgreSQL
-> Frontend / Admin Console
```

### 5.1 Source Layer 信息源层

信息源层负责稳定获取外部信号。P1 先接入低风险、容易冷启动的信息源，例如 HN Algolia API、官方 RSS 或稳定公开页面。X、Reddit、YouTube、Facebook 等复杂平台进入后续阶段。

这一层必须由工程代码控制。Agent 不应该自由决定去哪里抓、抓多少、如何绕过站点限制。

### 5.2 Workflow Layer 工作流编排层

工作流层建议使用 LangGraph。

它负责：

- 控制流程顺序。
- 维护 workflow state。
- 控制分支。
- 控制修订循环。
- 控制最大重试次数。
- 将失败节点标记为 failed 或 manual_review。
- 将每次运行记录为 pipeline_run。

它不负责：

- 自己判断事件价值。
- 自己写内容。
- 自己发布内容。
- 自由调用外部互联网。

### 5.3 Agent Layer 编辑部 Agent 层

Agent 层模拟真实编辑部的核心岗位。主 Agent 不是单纯的 prompt 节点，而是负责某个业务岗位的一组判断和决策。

P1 与终局共享三个主角色：

- 值班编辑 Agent。
- 研究写作 Agent。
- 审稿发布 Agent。

### 5.4 Tool / Skill Layer 能力层

能力层分为两类：

```text
能力型子 Agent / Skill：负责语义判断和生成。
工程 Tool：负责确定性动作。
```

子 Agent / Skill 可以被主 Agent 调用，也可以在后续版本升级为独立 Agent。

工程 Tool 必须白名单、限时、限次数，并记录调用结果。

### 5.5 Product Service Layer 产品服务层

产品服务层负责数据库写入、状态变更、发布、隐藏、重跑、后台操作记录和前台查询。

发布服务必须由工程代码实现。Agent 只能给出发布建议，不能直接写 `published_events`。

## 6. 编辑部式主 Agent

### 6.1 值班编辑 Agent

值班编辑 Agent 负责回答：

> 这件事值不值得做成一个事件？

职责：

- 判断信号是否 AI 相关。
- 对信号进行初步筛选。
- 判断多个信号是否属于同一事件。
- 识别事件类型。
- 判断事件热度、重要度和中文用户价值。
- 给出事件优先级。
- 给出写作角度。

输入：

- 标准化后的 source_signals。
- 基础热度指标。
- 来源类型。
- 已存在候选事件。
- 历史已发布事件。

输出：

- event_candidate 草案。
- 关联的 signal 列表。
- merge_reason。
- ranking_reason。
- suggested_angle。
- should_continue。

边界：

- 不写详情正文。
- 不直接发布。
- 不直接删除信号。
- 不做深度事实核验。

### 6.2 研究写作 Agent

研究写作 Agent 负责回答：

> 怎么把这件事讲清楚？

职责：

- 整理来源材料。
- 生成 research package。
- 生成首页事件卡。
- 生成事件详情正文。
- 生成为什么值得关注。
- 生成后续关注点。
- 根据审稿意见重写。

输入：

- event_candidate。
- 关联 source_signals。
- 原文摘要或缓存正文。
- 值班编辑 Agent 给出的角度。
- 审稿发布 Agent 的修订意见。

输出：

- event_dossier。
- card_title。
- card_summary。
- category。
- signal_label。
- detail_title。
- detail_summary。
- detail_body。
- why_it_matters。
- follow_up_points。
- source_refs。
- version。

边界：

- 不新增来源。
- 不自由浏览全网。
- 不把不确定爆料写成确定事实。
- 不直接修改 published_events。

### 6.3 审稿发布 Agent

审稿发布 Agent 负责回答：

> 这篇事件档案能不能发？

职责：

- 检查结构完整性。
- 检查标题和正文是否一致。
- 检查来源是否支撑正文。
- 检查是否过度推断。
- 检查是否像搬运原文。
- 检查是否标题党。
- 检查是否空泛。
- 给出 publish、revise、manual_review 或 reject 建议。

输入：

- event_dossier。
- source_refs。
- event_candidate。
- Agent 运行上下文。

输出：

- review_result。
- decision。
- risk_level。
- issues。
- revision_instructions。
- publish_summary。

边界：

- P1 不做完整真实性核验。
- 不直接发布。
- 不直接改写正文，改写由研究写作 Agent 执行。
- 不绕过人工处理状态。

## 7. 能力型子 Agent / Skill

能力型子 Agent / Skill 是主 Agent 可注册、可复用、可替换的智能能力。

终局可包含：

| Skill | 归属主 Agent | 作用 |
| --- | --- | --- |
| AI 相关性判断 Skill | 值班编辑 Agent | 判断信号是否属于 AI 圈 |
| 事件归并 Skill | 值班编辑 Agent | 判断多个信号是否是同一事件 |
| 选题角度 Skill | 值班编辑 Agent | 判断事件应该从技术、产品、公司、开源或行业角度解释 |
| 来源摘要 Skill | 研究写作 Agent | 将长来源压缩成可写作材料 |
| 事件卡生成 Skill | 研究写作 Agent | 生成首页卡片字段 |
| 详情正文写作 Skill | 研究写作 Agent | 生成自然中文详情正文 |
| 文风润色 Skill | 研究写作 Agent | 改善可读性和中文表达 |
| 搬运风险检查 Skill | 审稿发布 Agent | 检查是否过度接近原文 |
| 过度推断检查 Skill | 审稿发布 Agent | 检查来源是否支撑结论 |
| 修订建议 Skill | 审稿发布 Agent | 给出可执行的重写意见 |

P1 不要求所有 Skill 都独立实现。P1 可以先把部分 Skill 实现为结构化 LLM 调用，后续再升级为更完整的子 Agent。

判断标准：

> 需要语义判断、生成和审稿的，适合做 Skill 或子 Agent；确定性动作不应 Agent 化。

## 8. 工程 Tool

工程 Tool 负责确定性动作，必须白名单管理。

终局工具可以包括：

- `fetch_source_content(url)`：读取来源正文或缓存正文。
- `search_existing_candidates(query)`：查询相似候选事件。
- `search_published_events(query)`：查询历史已发布事件。
- `calculate_heat_score(signal)`：计算基础热度分。
- `normalize_url(url)`：URL 归一化。
- `make_source_hash(signal)`：生成来源幂等键。
- `load_candidate_signals(candidate_id)`：读取候选事件支撑信号。
- `save_artifact(content)`：保存中间产物。
- `record_agent_run(payload)`：记录 Agent 运行。

工具限制：

- 只允许白名单工具。
- 每个 Agent 节点有最大工具调用次数。
- 每个工具有 timeout。
- 工具参数需要校验。
- 工具调用结果要进入运行记录。
- 工具默认只读。
- 发布、隐藏、删除、状态流转不作为 Agent 可直接调用的工具。

P1 可以先不单独建设复杂 Tool 系统，但必须保留工具调用记录的承载位置。

## 9. LangGraph 工作流设计

LangGraph 用于编排状态机，不用于替代业务 Agent。

推荐主流程：

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

节点分类：

```text
工程节点：
collect_signals
normalize_signals
publish_or_manual_review
record_run

Agent 节点：
editorial_triage
merge_and_rank_events
build_research_package
draft_event_dossier
review_event_dossier
revise_if_needed
```

### 9.1 修订循环

内容生成后必须经过审稿。审稿结果决定分支：

```text
publish：进入工程发布服务。
revise：回到研究写作 Agent 修订。
manual_review：进入人工处理。
reject：丢弃或保留为 rejected。
```

修订循环必须有限制：

```text
最多修订 2 次。
超过 2 次仍不通过，进入 manual_review。
```

### 9.2 Workflow State

工作流状态至少包含：

- `run_id`
- `source_batch_id`
- `candidate_id`
- `dossier_id`
- `current_node`
- `status`
- `retry_count`
- `revision_count`
- `last_error`
- `agent_outputs`
- `review_decision`

P1 可以简化字段，但必须保留 `run_id`、状态、重试次数和关键输出引用。

## 10. 数据模型蓝图

数据库可以按新版生产线推倒重来。新模型不再被旧版 `EvidenceCard`、`EventCluster`、`ContentArtifact`、`Brief` 的命名限制。

核心生产链路为：

```text
Signal
-> EventCandidate
-> EventDossier
-> ReviewResult
-> PublishedEvent
```

### 10.1 sources

信息源配置表。

用途：

- 记录 HN、GitHub、官网、新闻站等来源。
- 记录来源类型、入口、启用状态和采集策略。

### 10.2 source_signals

外部信号表。

用途：

- 保存每条外部内容的标准化结果。
- 一条 HN story、一篇官网公告、一篇新闻站文章都先进入此表。

建议记录：

- source_id
- original_title
- original_url
- canonical_url
- published_at
- collected_at
- raw_summary
- content_excerpt
- content_hash
- content_cache_path
- heat_metrics
- source_hash
- fetch_status

### 10.3 event_candidates

候选事件表。

用途：

- 多个 source_signal 归并后形成内部候选事件。
- 候选事件不一定发布。

建议记录：

- candidate_title
- event_type
- category
- suggested_angle
- heat_score
- importance_score
- audience_value_score
- ranking_score
- ranking_reason
- status
- merge_reason
- idempotency_key

### 10.4 event_candidate_signals

候选事件和信号的关联表。

用途：

- 记录一个候选事件由哪些 signal 支撑。
- 支持后台追溯来源。

建议记录：

- candidate_id
- signal_id
- relation_type
- merge_confidence
- merge_reason

### 10.5 event_dossiers

事件档案草稿表。

用途：

- 保存研究写作 Agent 生成的内容。
- 同一个 candidate 可以多次生成或修订，因此需要版本号。

建议记录：

- candidate_id
- version
- card_title
- card_summary
- category
- signal_label
- cover_image_url
- detail_title
- detail_summary
- detail_body
- why_it_matters
- follow_up_points
- source_refs
- status
- generated_by_run_id

### 10.6 review_results

审稿结果表。

用途：

- 保存审稿发布 Agent 对 dossier 的检查结果。

建议记录：

- dossier_id
- decision
- risk_level
- issues
- revision_instructions
- checked_items
- reviewer_agent_run_id

decision 枚举：

```text
publish
revise
manual_review
reject
```

### 10.7 published_events

已发布事件表。

用途：

- 前台首页和详情页稳定读取此表。
- 发布时从通过审稿的 dossier 生成快照。

建议记录：

- candidate_id
- dossier_id
- published_title
- published_card_summary
- published_detail_body
- category
- signal_label
- cover_image_url
- source_refs
- published_at
- status
- publish_mode

publish_mode：

```text
auto
manual
```

### 10.8 pipeline_runs

流水线运行记录表。

用途：

- 记录一次完整生产任务。
- 支持后台查看本次跑了什么、成功多少、失败多少。

建议记录：

- run_id
- trigger_type
- source_scope
- status
- started_at
- ended_at
- summary
- error_message

### 10.9 agent_runs

Agent 运行记录表。

用途：

- 记录每个主 Agent、Skill 或 LLM 节点的运行情况。
- 后台监控 Agent 稳定性的核心数据。

建议记录：

- run_id
- agent_name
- agent_role
- input_summary
- output_json
- status
- model_provider
- model_name
- duration_ms
- retry_count
- error_message
- trace_json

P1 可以先把工具调用记录放在 `trace_json` 中。

### 10.10 tool_calls

工具调用记录表。

用途：

- 终局用于独立记录 Agent 调用工具的细节。

P1 可以不单独建表，后续从 `agent_runs.trace_json` 中拆出。

### 10.11 admin_actions

后台人工操作记录表。

用途：

- 记录管理员编辑、隐藏、恢复、发布、退回、重跑等动作。

建议记录：

- target_type
- target_id
- action_type
- before_snapshot
- after_snapshot
- reason
- created_at

## 11. 状态设计

event_candidate 状态建议：

```text
new
triaged
merged
drafting
reviewing
ready_to_publish
published
manual_review
rejected
failed
hidden
```

event_dossier 状态建议：

```text
draft
reviewing
needs_revision
approved
manual_review
rejected
published_snapshot
```

pipeline_run 状态建议：

```text
running
succeeded
partial_failed
failed
cancelled
```

P1 不需要复杂状态流，但必须避免只有成功和失败两种状态。Agent 系统的不稳定性要求系统能表达草稿、待审、需修订、人工处理和已发布。

## 12. 发布与人工干预边界

发布必须由工程发布服务执行。

Agent 可以输出：

- 发布建议。
- 修订建议。
- 风险说明。
- 人工处理建议。

Agent 不允许：

- 直接写 `published_events`。
- 直接隐藏已发布内容。
- 直接删除候选事件。
- 绕过 review_result。

自动发布条件：

- dossier 结构完整。
- 审稿发布 Agent 输出 `publish`。
- 来源链接存在。
- 未超过风险阈值。
- 工程幂等检查通过。

人工处理场景：

- 审稿输出 `manual_review`。
- 修订超过 2 次仍不通过。
- 来源不足。
- 事件过热但表达不确定。
- 疑似搬运原文。
- 事件归并冲突。

后台必须支持：

- 查看候选事件。
- 查看事件来源。
- 查看 Agent 运行记录。
- 编辑事件内容。
- 发布事件。
- 隐藏事件。
- 退回重写。
- 单条重跑。

## 13. 运行记录与可观测性

后台不仅是内容管理工具，也是 Agent 生产链路监控台。

P1 必须记录：

- pipeline run。
- Agent run。
- 每个节点状态。
- 输入摘要。
- 输出结构化结果。
- 错误信息。
- retry_count。
- revision_count。
- 发布记录。
- 人工操作记录。

终局可增强：

- 独立 tool_calls。
- token 和成本估算。
- 模型耗时统计。
- 节点成功率。
- 来源成功率。
- 失败原因聚合。
- 告警和重试队列。

## 14. 工程增强能力的阶段边界

终局可以支持队列、缓存、对象存储、向量检索、成本监控等工程能力，但 P1 不强制实现这些基础设施。

P1 必须预留：

- `run_id`
- `agent_run_id`
- 状态字段
- 幂等键
- `source_hash`
- `content_hash`
- `dossier.version`
- `review_result`
- `manual_review` 状态
- 运行记录
- 后台操作记录

P1 暂不做：

- Redis。
- Celery / RQ / Dramatiq 队列。
- S3 / MinIO 对象存储。
- 向量数据库。
- 复杂调度系统。
- 复杂监控大盘。
- 多用户权限。
- 多模型成本路由。
- 全平台社媒采集。

终局增强方向：

- 用队列支撑异步采集和生成。
- 用 Redis 支撑短期缓存和任务状态。
- 用对象存储保存 HTML、正文、图片和中间产物。
- 用 embedding / pgvector 提升事件归并和相似事件查询。
- 用成本统计控制 LLM 调用。
- 用 OpenTelemetry 或类似机制增强链路追踪。

## 15. LLMClient 边界

LLMClient 是模型调用底座，不是业务 Agent。

LLMClient 只负责：

- provider 切换。
- model 切换。
- api_key / base_url 配置。
- chat。
- stream_chat。
- OpenAI-compatible 调用。

LLMClient 不负责：

- 业务 prompt。
- Agent 状态。
- 工具绑定。
- 结构化 schema。
- repair 策略。
- 发布状态。
- 数据库写入。

结构化输出、工具绑定、多步修订和业务 prompt 应放在具体 Agent、Skill 或 workflow 节点中设计。

## 16. 质量门禁

P1 的质量门禁不是完整真实性核验。

P1 Quality Gate 只检查：

- 内容是否为空。
- 结构是否完整。
- 标题和正文是否一致。
- 是否缺少来源链接。
- 是否直接搬运原文。
- 是否过度夸张。
- 是否把不确定内容写成确定事实。
- 首页卡和详情内容是否成对存在。
- 详情正文是否能让中文用户读懂。

P2 或 P3 才考虑深度事实核查：

- 官方来源追溯。
- 多来源交叉验证。
- 争议事件标记。
- 事实级引用。
- 更正记录。

## 17. 阶段化落地路线

### 17.1 P1：最小硬核闭环

目标：

```text
用单机 Python Worker 跑通从外部信号到已发布事件档案的闭环。
```

范围：

- 至少一个稳定信息源。
- source_signals。
- event_candidates。
- event_dossiers。
- review_results。
- published_events。
- pipeline_runs。
- agent_runs。
- 值班编辑 Agent 的最小实现。
- 研究写作 Agent 的最小实现。
- 审稿发布 Agent 的最小实现。
- 最多 2 次修订循环。
- 后台可查看运行记录和内容状态。

不做：

- 完整晨报。
- 追问助手。
- 深度真实性核验。
- 社媒大规模采集。
- 队列和 Redis。
- 复杂 UI 管理台。

### 17.2 P1.5：内容组织增强

目标：

```text
基于已发布事件生成今日简报，并增强信息源和事件归并能力。
```

范围：

- 今日简报。
- GitHub Trending。
- Hugging Face Trending。
- Reddit / YouTube 的合规低风险入口。
- embedding 辅助事件归并。
- 更强后台批量操作。
- 更强失败兜底。

### 17.3 P2：交互与研究增强

目标：

```text
让用户围绕事件继续理解和追问。
```

范围：

- 事件追问助手。
- 事件追踪时间线。
- 更多来源补充。
- 专题聚合。
- 用户收藏。
- 更成熟的后台。

### 17.4 P3：产品化与规模化

目标：

```text
从个人可用工具升级为更完整的 AI 情报产品。
```

范围：

- 个性化订阅。
- 多用户体系。
- 队列化生产。
- 成本监控。
- 对象存储。
- 复杂监控大盘。
- 深度事实核查。

## 18. 风险与应对

### 18.1 过度工程化风险

风险：终局架构完整，但如果第一版全部做满，会拖慢交付。

应对：文档描述终局蓝图，实现按 P1、P1.5、P2、P3 分批落地。

### 18.2 假 Agent 化风险

风险：每个 prompt 都叫 Agent，会显得虚。

应对：主 Agent 对应真实业务岗位，Skill 对应可复用语义能力，确定性动作保持为 Tool。

### 18.3 成本和延迟风险

风险：多 Agent 多轮调用会带来成本和延迟。

应对：P1 控制节点数量、限制修订次数、保留缓存和模型分层空间。

### 18.4 事件归并风险

风险：错误合并会让事件内容混乱。

应对：P1 采用宁可重复、不乱合并原则。规则预筛加 Agent 判断，后台允许人工修正。

### 18.5 自动发布风险

风险：P1 不做深度事实核验，自动发布可能放大不确定内容。

应对：审稿发布 Agent 必须识别不确定表达，风险内容进入 manual_review。

### 18.6 数据模型复杂风险

风险：终局表较多，增加开发负担。

应对：P1 落核心表和必要字段，`tool_calls`、复杂成本统计等可后续拆出。

## 19. 与旧版架构的关系

旧版架构中的以下内容可以作为历史参考：

- HN 冷启动采集。
- 原文缓存。
- Pipeline run。
- Agent stub。
- Quality Gate stub。
- pytest 和运行报告。

旧版架构中的以下内容不再作为未来命名和设计约束：

- EvidenceCard 作为核心业务对象。
- EventCluster 作为核心业务对象。
- ContentArtifact 作为核心内容对象。
- BriefWriterAgent 进入 P1 主链路。
- 晨报优先。

新版概念映射：

| 旧概念 | 新概念 |
| --- | --- |
| EvidenceCard | source_signal + AI 理解结果 |
| EventCluster | event_candidate |
| ContentArtifact | event_dossier |
| QualityGateResult | review_result |
| PublishedEvent | published_event |
| Brief / BriefItem | P1.5 brief 能力 |

产品形态和 PRD v2.0 不推翻。重构对象是 Agent 架构、数据模型和后续工程路线。

## 20. 下一步

在本文档确认后，下一步应更新技术架构与数据模型设计，使其与新版 Agent 系统设计对齐。

后续进入实现计划前，应先完成：

1. 明确 P1 最小数据表字段。
2. 明确 LangGraph workflow state。
3. 明确三个主 Agent 的输入输出 schema。
4. 明确 P1 哪些 Skill 先合并实现，哪些后续拆分。
5. 明确后台最小监控页面需要展示哪些运行记录。

完成这些后，再进入 `superpowers:writing-plans` 阶段，拆出可执行的开发计划。
