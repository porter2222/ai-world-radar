# QFT 晨报项目参考价值调研

更新时间：2026-06-04

本报告分析本地项目 `D:\qft-agent-project\qft-morning-brief` 对 AI World Radar 后续采集系统、证据系统、Agent 生产链路和质量门禁的参考价值。

调研结论很明确：`qft-morning-brief` 不适合作为 AI World Radar 的直接依赖，也不能直接复用它的业务 SQL、房屋租赁指标和老板晨报话术；但它非常适合作为“Agent 自动生产内容如何保持可追溯、可审计、可质检”的工程样板。

## 1. 调研目的

AI World Radar 的核心不是普通 AI 新闻聚合，也不是让一个大模型自由上网总结，而是把多源碎片信息加工成：

- 可回源的 AI 事件。
- 可解释的 Evidence Card。
- 可合并的 Event Cluster。
- 可自动发布但可事后校正的中文情报内容。

`qft-morning-brief` 虽然业务领域不同，但它已经实现了一条相似的闭环：

```text
业务源数据
  -> 查询工具 / Source Packet
  -> 候选问题发现
  -> 候选准入与排序
  -> Issue Evidence Pack
  -> LLM 结构化生成
  -> Quality Gate
  -> PG 审计落库
  -> 报告展示 / 追问
```

这条链路对 AI World Radar 的价值在于：它证明了“Agent-first 产品”不能只靠提示词，必须有证据层、候选层、质量门禁和运行审计。

## 2. 项目概况

项目路径：

```text
D:\qft-agent-project\qft-morning-brief
```

项目定位：

```text
AI 驱动的全房通经营晨报系统，为房屋租赁企业老板每日生成结构化经营简报。
```

技术栈：

- Next.js / React / TypeScript。
- Zod schema。
- Drizzle ORM。
- PostgreSQL 作为晨报系统审计库。
- MySQL 作为业务只读数据源。
- OpenAI Responses API / Agents SDK 双运行时。
- Node test runner + tsx 测试。

项目协作文档中的架构描述是：

```text
MySQL（业务数据）-> 查询工具（预取）-> LLM structured output -> PG 落库（审计）
```

对 AI World Radar 来说，这个项目不是采集外网新闻的参考，而是“数据进入系统后，如何变成可信内容”的参考。

## 3. 总体结论

### 3.1 高价值参考点

`qft-morning-brief` 对 AI World Radar 最有价值的部分是：

1. `source_packets` 原始证据包。
2. `tool_call_records` 工具调用审计。
3. `generation_runs` Agent 运行审计。
4. `evidenceRef` 证据引用结构。
5. `CandidateIssue` 候选项 schema。
6. `sourceAdmission` 证据准入机制。
7. 规则发现 + LLM 发现的 compare 模式。
8. 候选晋级和排序 gate。
9. `IssueEvidencePack` 证据包构造。
10. `Quality Gate` 对输出内容做证据校验。
11. deterministic fallback。
12. 基于最新 QC 通过报告的追问链路。

### 3.2 不应照搬的部分

以下内容不应迁移到 AI World Radar：

- 房屋租赁领域 SQL。
- 全房通业务指标。
- 四大抓手、老板晨报、派单等级等业务话术。
- `customerId` / `company_id` 这类租赁企业隔离模型。
- 财务对账和业务 metric release gate 的具体规则。
- 当前项目中的中文业务文案和乱码历史内容。
- 面向老板晨报的页面结构。

AI World Radar 需要借鉴的是工程模式，不是业务语义。

### 3.3 推荐采用方式

推荐策略：

- P1：借鉴证据层、运行审计、最小质量门禁。
- P1.5：借鉴候选池、规则排序、LLM/rules compare、失败兜底。
- P2：借鉴事件级 AI 追问和工具化深挖。

不推荐策略：

- 不要一开始复制完整多 Agent 流程。
- 不要让写作 Agent 直接读取网页或原始长文。
- 不要让 LLM 生成没有 EvidenceRef 的公开内容。
- 不要把热度源、线索源直接当事实源。

## 4. 与 AI World Radar 的关系

AI World Radar 已经确定 P1 主链路：

```text
Source Registry
  -> Source Collector
  -> Raw Item Store
  -> Extract / Normalize
  -> Evidence Card Agent
  -> Candidate Router Agent
  -> Event Cluster Agent
  -> Event Ranking Agent
  -> Content Planning Agent
  -> Content Generation Agent
  -> Quality Gate Agent
```

`qft-morning-brief` 对应的内部链路可以映射为：

```text
fetchMorningBriefPacketBundle
  -> source_packets
  -> runDiscoveryAgent
  -> runInvestigationPreflight
  -> runSelectionAgent
  -> buildIssueEvidencePack
  -> runMorningAgentWithTelemetry
  -> runQualityGate
  -> persistMorningBriefSuccess / Failure
```

核心相似点：

- 都不是简单列表聚合，而是从原始材料中提取“值得展示的事项”。
- 都需要把原始输入和公开输出隔离，中间用证据结构连接。
- 都需要自动发布，因此必须有质量门禁和失败记录。
- 都需要把 Agent 生成结果限制在证据范围内。

核心差异：

- QFT 面向结构化业务数据，AI World Radar 面向网页、RSS、API、社群热度和新闻线索。
- QFT 的事实源通常是内部数据库，AI World Radar 的事实源是官方公告、博客、GitHub、HF、论文、HN 等公开来源。
- QFT 的候选对象是经营问题，AI World Radar 的候选对象是 AI 事件。
- QFT 的质量风险是业务数据错配，AI World Radar 的质量风险是事实误写、传闻确认化、来源污染、版权和标题党。

## 5. 关键源码参考

### 5.1 主编排链路

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\server\services\morning-brief.ts
```

关键函数：

```text
runSingleCustomerMorningBrief
```

它完成的工作包括：

1. 生成 `runId`。
2. 在非 `force` 模式下跳过已通过 QC 的报告。
3. 调用 `fetchMorningBriefPacketBundle` 采集本轮数据包。
4. 调用 `runDiscoveryAgent` 做候选发现。
5. 调用 `runInvestigationPreflight` 做候选预检。
6. 调用 `runSelectionAgent` 做候选排序和 Top 选择。
7. 对入选候选构造 `IssueEvidencePack`。
8. 持久化初始阶段 `source_packets`。
9. 调用 `runMorningAgentWithTelemetry` 生成报告。
10. 必要时进行 rubric/reflexion 重跑。
11. 进行 deep dive、sanitize、normalize。
12. 持久化最终阶段 `source_packets`。
13. 调用 `runQualityGate`。
14. 成功或失败都写入审计表。

对 AI World Radar 的参考价值：

- P1 应该也有一个清晰的 `runDailyRadarPipeline` 或 `runEventProductionPipeline`，不要让采集、聚合、生成、发布散落在各处。
- 每次运行都要有 `runId`，贯穿 raw snapshot、evidence card、event cluster、content artifact、quality gate。
- 失败也要落库，不能只写日志。

建议 AI World Radar P1 对应设计：

```text
runRadarProduction(input)
  -> collectSources(runId)
  -> normalizeRawItems(runId)
  -> buildEvidenceCards(runId)
  -> routeCandidateEvents(runId)
  -> clusterEvents(runId)
  -> rankEvents(runId)
  -> generateContent(runId)
  -> qualityGate(runId)
  -> publishOrHold(runId)
```

### 5.2 Source Packet 与工具调用审计

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\server\services\morning-brief-packets.ts
D:\qft-agent-project\qft-morning-brief\lib\server\services\morning-brief-persistence.ts
D:\qft-agent-project\qft-morning-brief\lib\db\schema.ts
```

QFT 的 `fetchMorningBriefPacketBundle` 会将多个数据源包装为 packet，并通过 `withToolCallRecord` 记录工具调用。部分工具失败时采用 fail-open，例如账单覆盖数据失败时返回空 packet，而不是让全链路崩掉。

数据库中有三类对 AI World Radar 很重要的表：

- `generation_runs`：记录 runId、是否成功、耗时、模型、运行时、token、promptVersion、qualityGateVersion、错误。
- `source_packets`：记录 runId、packetDate、packetType、payload、sourceVersion、fetchedAt。
- `tool_call_records`：记录 runId、toolName、status、durationMs、errorMsg、startedAt、finishedAt。

对 AI World Radar 的参考价值：

- P1 的采集系统要保存 raw snapshot，不只是保存最终事件。
- 每个 adapter 都应有 source version / adapter version。
- 每次抓取失败要分类记录，后续才能做 source health。
- 失败要支持降级，不要因为一个低价值源失败导致整天内容不可用。

建议 AI World Radar P1 表设计参考：

```text
collector_runs
  id
  run_id
  started_at
  finished_at
  success
  failure_count
  model
  prompt_version
  quality_gate_version

raw_snapshots
  id
  run_id
  source_id
  adapter_id
  source_url
  fetch_method
  status_code
  response_hash
  raw_body
  fetched_at
  error_type

raw_items
  id
  snapshot_id
  source_id
  canonical_url
  title
  published_at
  language
  raw_excerpt
  normalized_payload

source_health_events
  id
  source_id
  run_id
  status
  error_type
  error_message
  duration_ms
```

### 5.3 EvidenceRef 证据引用模型

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\contracts\report.schema.ts
```

QFT 的核心证据引用模型：

```ts
evidenceRefSchema = {
  toolName: string,
  fieldPath: string,
  rawValue: string | number | boolean,
  displayValue?: string
}
```

这个设计非常适合 AI World Radar 改造。AI World Radar 的公开事件内容必须能回答：

- 这句话来自哪个来源？
- 原始 URL 是什么？
- 原始抓取快照是什么？
- Evidence Card 是哪一张？
- 引用的是原文、标题、发布时间、热度数字还是模型推断？
- 这个证据是事实源、热度源还是线索源？

建议 AI World Radar 改造版：

```ts
type EvidenceRef = {
  sourceId: string;
  sourceName: string;
  sourceLevel: "fact" | "heat" | "lead";
  rawSnapshotId: string;
  rawItemId: string;
  evidenceCardId?: string;
  url: string;
  fieldPath: string;
  rawValue?: string | number | boolean;
  quote?: string;
  capturedAt: string;
  confidence: "high" | "medium" | "low";
}
```

注意事项：

- `quote` 只能保存短摘，不要保存大段正文，避免版权风险。
- 热度数字需要保存采集时间，因为点赞、评论、star 会变化。
- 对二手聚合源要标注 `sourceLevel=lead`，不能直接支撑事实结论。

### 5.4 CandidateIssue 到 CandidateEvent

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\contracts\candidate-issue.schema.ts
```

QFT 的 `CandidateIssue` 包含：

- `issueCode`
- `issueType`
- `priorityTier`
- `category`
- `severity`
- `titleHint`
- `quantification`
- `attribution`
- `scope`
- `evidenceWindow`
- `evidenceRefs`
- `dataStatus`
- `canPromote`
- `mergeGroup`
- `promotionReason`
- `sourceAdmission`

AI World Radar 可以改造为 `CandidateEvent`：

```ts
type CandidateEvent = {
  eventKey: string;
  eventType:
    | "model_release"
    | "product_launch"
    | "research_paper"
    | "open_source_release"
    | "company_news"
    | "policy_safety"
    | "community_discussion"
    | "funding_acquisition"
    | "tool_trend";
  priorityTier: "p0" | "p1" | "p2" | "watch";
  titleHint: string;
  subject: string;
  trigger: string;
  eventTime?: string;
  evidenceWindow: "last_24h" | "last_72h" | "last_7d" | "evergreen";
  evidenceRefs: EvidenceRef[];
  sourceAdmission: SourceAdmission;
  heatSignals?: HeatSignal[];
  dataStatus: "complete" | "partial" | "missing";
  canPromote: boolean;
  mergeGroup?: string;
  promotionReason?: string;
}
```

参考价值：

- 候选事件必须是结构化对象，不能只是 LLM 的一段文字。
- 是否能公开发布应该由 `canPromote`、`sourceAdmission`、`dataStatus` 和 `evidenceRefs` 共同决定。
- `mergeGroup` 对事件聚合很有用，例如同一个模型发布在 OpenAI News、HN、GitHub、X 同时出现。

### 5.5 Source Admission 证据准入

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\server\domain\evidence-admission.ts
```

QFT 将证据分成：

- `hard`
- `supporting`
- `blocked`

AI World Radar 非常需要类似机制，因为信息源天然分层：

- 事实源：官方公告、官方博客、GitHub release、论文页、HF model page。
- 热度源：HN、GitHub Trending、HF Trending、Reddit、YouTube、X。
- 线索源：TLDR AI、AIBase、竞品网站、Newsletter、中文聚合站。

建议 AI World Radar 的 `SourceAdmission`：

```ts
type SourceAdmission = {
  factEligible: boolean;
  heatEligible: boolean;
  leadOnly: boolean;
  status:
    | "official_fact"
    | "primary_asset"
    | "community_heat"
    | "aggregator_lead"
    | "unverified_rumor"
    | "blocked_tos_risk"
    | "blocked_low_quality";
  promotionPolicy: "normal" | "downgrade" | "watch" | "exclude";
  blockers?: string[];
  warnings?: string[];
}
```

质量门禁规则：

- 只有 `factEligible=true` 的证据能支撑“某事已经发生”。
- `heatEligible=true` 可以支撑“外网正在讨论”。
- `leadOnly=true` 只能进入待核验线索，不能进入公开事实描述。
- `blocked_tos_risk` 不进入 P1 自动链路。

### 5.6 Discovery / Selection 双阶段

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\server\services\discovery-agent.ts
D:\qft-agent-project\qft-morning-brief\lib\server\services\selection-agent.ts
D:\qft-agent-project\qft-morning-brief\lib\server\pipeline\promote-issues.ts
```

QFT 将候选处理拆成两层：

1. Discovery：发现候选。
2. Selection：从候选里选出最值得展示的 Top 项。

Discovery 支持：

- 规则扫描。
- LLM 发现。
- rules / llm / compare 模式。
- 候选去重。
- explainability 和 diff packet。

Selection 支持：

- 规则晋级和排序。
- LLM 选择。
- fallback 到规则结果。
- 候选资格卡 `CandidateQualificationCard`。

对 AI World Radar 的参考价值：

- P1 可以先用规则 + 简单 LLM 判断发现候选事件。
- P1.5 再引入 compare 模式，用于比较规则和 LLM 的差异。
- Event Ranking 不应该只让 LLM 排序，应先有可解释的规则分。

AI World Radar 可用的候选 gate：

```text
source_admission
  来源是否足以支撑事实或热度

data_status
  标题、链接、发布时间、来源是否完整

freshness
  是否处于 24h / 72h / 7d 窗口

event_shape
  是否能说成“谁/什么发生了什么变化”

duplication
  是否已被同一事件 cluster 吸收

source_diversity
  是否有多源支持，或是否为官方一手源

heat_signal
  是否有 HN 分数、GitHub star、HF trending、社区评论等热度信号

publishability
  是否能生成谨慎、可追溯、非标题党的前台内容
```

### 5.7 IssueEvidencePack 到 EventEvidenceBundle

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\server\domain\issue-evidence-pack.ts
```

QFT 的 `buildIssueEvidencePack` 会针对每个入选候选构造：

- issueCode。
- titleHint。
- primaryEvidenceRefs。
- scope。
- relatedEntities。
- snapshot。
- metrics。
- evidenceSummary。
- evidenceItems。
- rawEvidence。

AI World Radar 应改造为 `EventEvidenceBundle`：

```ts
type EventEvidenceBundle = {
  eventKey: string;
  titleHint: string;
  subject: string;
  trigger: string;
  primaryEvidenceRefs: EvidenceRef[];
  supportingEvidenceRefs: EvidenceRef[];
  heatEvidenceRefs: EvidenceRef[];
  sourceSummary: {
    officialSources: string[];
    communitySources: string[];
    leadSources: string[];
  };
  uncertainty: string[];
  rawItems: Array<{
    rawItemId: string;
    sourceName: string;
    title: string;
    url: string;
    publishedAt?: string;
  }>;
}
```

参考价值：

- 写作 Agent 不应该拿全部 raw body，而应该拿被压缩过的 evidence bundle。
- Evidence bundle 要保留原始 ID，便于详情页展示来源和管理页追溯。
- 对同一事件应区分 primary evidence、supporting evidence 和 heat evidence。

### 5.8 Quality Gate

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\server\pipeline\quality-gate.ts
D:\qft-agent-project\qft-morning-brief\tests\quality-gate-finance-ledger.test.ts
```

QFT 的 `runQualityGate` 会做几类检查：

- 输出 schema 是否有效。
- 面向用户的文案是否含禁用词。
- Top 项数量和数据质量是否匹配。
- 每个公开项是否有 evidenceRefs。
- evidenceRef 的 `toolName` 是否来自本轮真实工具调用。
- evidenceRef 的 `fieldPath/rawValue` 是否能在工具响应中匹配。
- 被标记为 blocked / supporting-only 的字段不能支撑硬结论。

这是 AI World Radar P1 最应该借鉴的部分。

AI World Radar 的 Quality Gate 应至少检查：

```text
Q1 schema_valid
  事件卡、详情页、简报 JSON schema 必须通过。

Q2 evidence_required
  每个公开事实句必须能追到 EvidenceRef。

Q3 source_level_match
  事实描述只能由 fact source 支撑；热议描述只能写成“外网讨论/社区关注”。

Q4 rumor_not_confirmed
  待核验线索不能写成确定事实。

Q5 date_consistency
  发布时间、抓取时间、事件时间不能自相矛盾。

Q6 no_direct_copy
  不能大段搬运竞品或新闻正文。

Q7 title_not_clickbait
  标题不能夸大、断言未确认结果。

Q8 source_count
  非官方事实最好有两个以上来源；官方一手源可单源发布。

Q9 raw_snapshot_exists
  EvidenceRef 指向的 raw snapshot/raw item 必须存在。

Q10 stale_heat_signal
  热度数字必须带采集时间，过期热度不能当实时热度。
```

推荐 P1 做法：

- Quality Gate 先用确定性代码做，不要完全交给 LLM。
- LLM 可以辅助判断“标题党、夸大、表达不清”，但不能替代 evidence existence check。
- gate 结果要写入数据库，管理页能看到失败原因。

### 5.9 Agent Runtime 与 fallback

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\server\agents\agent-runtime.ts
D:\qft-agent-project\qft-morning-brief\lib\server\openai-runtime.ts
D:\qft-agent-project\qft-morning-brief\lib\server\agents\morning-agent.ts
```

QFT 做了几件值得参考的事：

- Responses API 用于 schema-constrained structured output。
- Agents SDK 用于工具化、多轮、追问类场景。
- 运行时集中处理 provider target、model、fallback。
- `runMorningAgentWithTelemetry` 在没有 API key 或模型失败时走 deterministic fallback。
- telemetry 中记录 model、runtime、tokens、cost、providerResponseId、renderMode、error。

AI World Radar 建议：

- P1 内容生成优先用 Responses API + Zod schema。
- P1 不必引入复杂工具调用 Agent。
- P1 必须有 deterministic fallback：没有候选就少发，不要硬凑。
- P1.5 再引入多模型 compare 或更复杂的 agent runtime。
- P2 追问助手再考虑 Agents SDK 和工具调用。

### 5.10 Follow-up 追问

关键文件：

```text
D:\qft-agent-project\qft-morning-brief\lib\server\services\followup.ts
D:\qft-agent-project\qft-morning-brief\lib\server\agents\chat-agent.ts
D:\qft-agent-project\qft-morning-brief\app\api\chat\route.ts
```

QFT 的追问链路特点：

- 通过 SSE 输出。
- 基于最新 QC passed 的报告。
- 输入包含用户问题、历史消息、sessionId。
- 如果没有 API key 或 mock 模式，则返回 mock chat events。

AI World Radar 的应用方式：

- P1 不做 AI 追问助手。
- P2 可以基于事件详情页的 EventEvidenceBundle 做追问。
- 追问 Agent 只能读当前事件的 evidence bundle 和公开来源，不允许自由上网。
- 每次追问应返回引用来源，避免变成通用聊天。

建议 P2 追问上下文：

```text
event_cluster
event_detail
event_evidence_bundle
raw_item_source_list
quality_gate_result
user_question
chat_history
```

## 6. QFT 到 AI World Radar 的映射表

| QFT 概念 | QFT 源码位置 | AI World Radar 对应概念 | 推荐阶段 |
|---|---|---|---|
| `runSingleCustomerMorningBrief` | `lib/server/services/morning-brief.ts` | `runRadarProduction` 主生产链路 | P1 |
| `fetchMorningBriefPacketBundle` | `lib/server/services/morning-brief-packets.ts` | Source Collector / Raw Snapshot Builder | P1 |
| `source_packets` | `lib/db/schema.ts` | Raw Snapshot / Raw Item Store | P1 |
| `tool_call_records` | `lib/db/schema.ts` | Collector Call / Adapter Run Log | P1 |
| `generation_runs` | `lib/db/schema.ts` | Agent Run / Pipeline Run Audit | P1 |
| `evidenceRefSchema` | `lib/contracts/report.schema.ts` | EvidenceRef | P1 |
| `candidateIssueSchema` | `lib/contracts/candidate-issue.schema.ts` | CandidateEvent schema | P1 |
| `sourceAdmission` | `candidate-issue.schema.ts`, `evidence-admission.ts` | SourceAdmission / Source Level | P1 |
| `runDiscoveryAgent` | `lib/server/services/discovery-agent.ts` | Candidate Router / Event Discovery | P1 / P1.5 |
| `runSelectionAgent` | `lib/server/services/selection-agent.ts` | Event Ranking / Content Planning | P1 / P1.5 |
| `promoteIssues` | `lib/server/pipeline/promote-issues.ts` | Candidate gate / publishability gate | P1.5 |
| `buildIssueEvidencePack` | `lib/server/domain/issue-evidence-pack.ts` | EventEvidenceBundle | P1 |
| `runQualityGate` | `lib/server/pipeline/quality-gate.ts` | Quality Gate Agent / deterministic gate | P1 |
| `runMorningAgentWithTelemetry` | `lib/server/agents/morning-agent.ts` | Content Generation Agent | P1 |
| `runFollowup` | `lib/server/services/followup.ts` | Event AI Follow-up Assistant | P2 |
| stage compare packets | `morning-brief-agent-contracts.ts` | rules vs LLM explainability packet | P1.5 |
| replay tests | `tests/morning-brief-orchestration-harness.test.ts` | pipeline replay / regression tests | P1.5 |

## 7. 推荐给 AI World Radar 的最小架构

### 7.1 P1 最小闭环

P1 不需要完整复制 QFT 的多阶段 Agent。建议最小闭环：

```text
Source Registry
  -> Collector Run
  -> Raw Snapshot
  -> Raw Item
  -> Evidence Card
  -> Candidate Event
  -> Event Cluster
  -> Event Ranking
  -> Content Artifact
  -> Quality Gate
  -> Publish / Hold
```

### 7.2 P1 表结构方向

建议最小数据表：

```text
sources
source_adapters
collector_runs
raw_snapshots
raw_items
evidence_cards
candidate_events
event_clusters
event_cluster_evidence
content_artifacts
quality_gate_results
generation_runs
```

### 7.3 P1 Agent 输入边界

写作 Agent 输入必须是：

- Event Cluster。
- EventEvidenceBundle。
- 已归一化来源列表。
- 不确定性列表。
- 允许使用的短摘。

写作 Agent 不应直接拿：

- 整页 HTML。
- 竞品长文章正文。
- 未标注来源等级的 raw text。
- X / Reddit / YouTube 评论长串。

### 7.4 P1 Quality Gate 最小实现

P1 必须有确定性检查：

```text
schema valid
evidence ref exists
raw item exists
source level matches claim type
no unsupported hard claim
no stale date
no duplicate published event
no empty source list
```

P1 可以暂缓：

- LLM rubric 打分。
- reflexion 重跑。
- 多模型对比。
- 复杂人工审核工作流。

## 8. 分阶段建议

### 8.1 P1

目标：先跑通“稳定来源 -> 事件 -> 中文内容 -> 自动发布 -> 可追溯”。

从 QFT 借鉴：

- `runId` 贯穿全链路。
- Raw Snapshot / Source Packet 思路。
- EvidenceRef。
- CandidateEvent schema。
- SourceAdmission。
- deterministic fallback。
- generation run 审计。
- 最小 Quality Gate。

暂不借鉴：

- 复杂 compare 模式。
- rubric/reflexion 重跑。
- 事件级 AI 追问。
- Agents SDK 工具化多轮。

### 8.2 P1.5

目标：从“能跑”变成“更稳定、更可解释”。

从 QFT 借鉴：

- rules / LLM compare。
- 候选池。
- 候选资格卡。
- Event Ranking gate。
- source health。
- replay-friendly stage packets。
- 离线规则回放和回归测试。

适合加入：

- GitHub Trending / HF Trending 每日快照。
- HN 热度信号。
- YouTube 已知频道或视频 API。
- Reddit 指定 subreddit。
- 多源事件聚合增强。

### 8.3 P2

目标：形成差异化，而不只是新闻聚合。

从 QFT 借鉴：

- SSE 追问链路。
- 基于 QC passed 内容的上下文。
- chat history。
- 工具化深挖。
- 事件详情页内 AI follow-up。

AI World Radar P2 追问的原则：

- 只围绕当前事件追问。
- 只基于 EventEvidenceBundle 和允许工具回答。
- 回答必须带来源。
- 不把追问变成通用搜索或自由上网。

## 9. 后续开发 Agent 操作建议

后续开发 Agent 如果要参考 QFT 项目，建议按以下顺序读源码：

1. `D:\qft-agent-project\qft-morning-brief\AGENTS.md`
2. `D:\qft-agent-project\qft-morning-brief\lib\server\services\morning-brief.ts`
3. `D:\qft-agent-project\qft-morning-brief\lib\db\schema.ts`
4. `D:\qft-agent-project\qft-morning-brief\lib\contracts\report.schema.ts`
5. `D:\qft-agent-project\qft-morning-brief\lib\contracts\candidate-issue.schema.ts`
6. `D:\qft-agent-project\qft-morning-brief\lib\server\domain\evidence-admission.ts`
7. `D:\qft-agent-project\qft-morning-brief\lib\server\services\discovery-agent.ts`
8. `D:\qft-agent-project\qft-morning-brief\lib\server\services\selection-agent.ts`
9. `D:\qft-agent-project\qft-morning-brief\lib\server\domain\issue-evidence-pack.ts`
10. `D:\qft-agent-project\qft-morning-brief\lib\server\pipeline\quality-gate.ts`
11. `D:\qft-agent-project\qft-morning-brief\lib\server\agents\morning-agent.ts`
12. `D:\qft-agent-project\qft-morning-brief\lib\server\services\followup.ts`

不要从 UI 页面开始读。这个项目最有价值的不是展示层，而是服务端生产链路和审计链路。

## 10. 风险和限制

### 10.1 领域错配

QFT 是结构化业务数据系统，AI World Radar 是公开互联网信息系统。QFT 的数据可信度来自内部数据库，AI World Radar 的可信度来自来源分层和多源回溯。因此不能直接把 QFT 的“数据库字段级证据”理解为 AI World Radar 的“网页证据”。

### 10.2 复杂度风险

QFT 已经积累了较多业务 gate、rubric、reflexion 和测试。如果 AI World Radar P1 直接照搬，会导致 MVP 过重。P1 应先保留必要骨架：

- EvidenceRef。
- SourceAdmission。
- Quality Gate。
- run audit。

其他复杂机制后移。

### 10.3 LLM 过度参与风险

QFT 的经验反而说明：越是 Agent-first，越要把关键判断工程化。AI World Radar 不应让 LLM 替代采集、去重、证据存在校验和来源准入。

### 10.4 追问提前化风险

QFT 已有追问能力，但 AI World Radar P1 文档明确不包含 AI 追问助手。追问应作为 P2 能力，等事件详情页、证据层和质量门禁稳定后再做。

## 11. 最终建议

AI World Radar 后续开发可以把 `qft-morning-brief` 当成三个层面的参考：

1. 证据层参考：如何保存 source packet、EvidenceRef、raw value、field path、run audit。
2. 候选层参考：如何把原始输入变成候选，再用 gate 决定是否晋级。
3. 质量层参考：如何在自动发布前检查输出是否真的被证据支撑。

最推荐优先落地的是：

```text
Raw Snapshot
  -> Raw Item
  -> Evidence Card
  -> Candidate Event
  -> EventEvidenceBundle
  -> Content Artifact
  -> Quality Gate Result
```

一句话总结：

> QFT 项目对 AI World Radar 的最大价值，不是“怎么采集数据”，而是“怎么让 Agent 生成的内容仍然有证据、有审计、有门禁”。这正是 AI World Radar 从新闻聚合站变成 AI 情报雷达的关键。
