# GitHub趋势信号去重与新鲜度策略设计

更新时间：2026-06-26

## 1. 设计结论

本次修复的核心结论是：

> `github_repo_trends` 是热度雷达信号，不是天然新闻事件。它可以帮助系统发现值得关注的仓库，但不能因为每次被抓到就反复生成首页事件。

P1 修复采用“趋势源冷却期 + 强新鲜度证据豁免 + 已有重复数据治理”的策略：

- 同一个 GitHub 仓库在最近 7 天内已经发布过首页事件时，新的 `github_repo_trends` 快照默认不再生成新事件。
- 如果同一仓库的新信号来自 GitHub Release、官方公告、HN 高热讨论等更强的新鲜度来源，则不受趋势冷却期限制。
- 纯 GitHub repo trend 信号被跳过时，要记录跳过原因，而不是静默丢弃。
- 当前数据库里已经存在的重复趋势事件，需要通过一次性治理把旧重复事件从首页隐藏，避免用户继续看到 Hermes-agent 这类重复卡片。

这不是前端展示问题，也不是排序问题，而是后端“信号新鲜度”和“跨轮去重”规则缺失。

## 2. 当前问题复盘

以 `NousResearch/hermes-agent` 为例，当前数据库中已经出现多条已发布事件：

- 2026-06-26：开源 AI agent 项目 hermes-agent 获得 GitHub 开发者关注。
- 2026-06-24：NousResearch 的 hermes-agent 进入开源 Agent 项目观察视野。
- 2026-06-24：NousResearch/hermes-agent 仓库被外网开发者讨论。
- 2026-06-24：开源 AI Agent 项目 hermes-agent 引发开发者关注。

这些卡片都指向同一个 GitHub 仓库，但因为每次采集的 `snapshot_bucket` 不同，系统把它们当成了不同信号，后续 LLM 又生成了不同的 `candidate_key`，最终绕过了 `PublishedEvent.candidate_id` 的幂等约束。

当前链路中的关键事实：

```text
github_repo_trends
-> source_hash = github_repo_trends:{owner/repo}:{snapshot_bucket}
-> published_at = detected_at
-> candidate_key 由 LLM 或 selector 生成，可能每轮不同
-> PublishedEvent 只按 candidate_id 幂等
```

因此，当前系统能防住“同一个 candidate 重复发布”，但防不住“同一个仓库换一个 candidate_key 再发布一次”。

## 3. 概念边界

### 3.1 真实事件信号

真实事件信号是指本身带有明确事件发生语义的来源，例如：

- OpenAI / Anthropic / NVIDIA / Google DeepMind 等官方公告。
- GitHub Release。
- HN 帖子。
- 论文、博客、产品发布页。

这类信号的 `published_at` 可以近似理解为事件时间，能够直接参与“最近发生了什么”的判断。

### 3.2 趋势检测信号

趋势检测信号是指系统在某一时刻发现某个对象仍有热度，例如：

- GitHub 仓库搜索结果仍排名靠前。
- star 数继续增长。
- 仓库最近被 push 或 updated。

这类信号的 `detected_at` 只能说明“此刻被检测到仍有热度”，不能直接等价于“此刻发生了一条新新闻”。

`github_repo_trends` 属于趋势检测信号。

## 4. 目标与非目标

### 4.1 目标

- 阻止同一个 GitHub 仓库在短时间内被反复发布到首页。
- 保留 GitHub repo trends 的发现价值。
- 不让 LLM 自由决定是否重复发布，去重规则必须由工程代码兜底。
- 不新增数据库表，优先复用现有 `SourceSignal.status`、`metadata_json`、`PublishedEvent.status`。
- 修复当前首页已有重复卡片的可见性问题。
- 为后续后台管理页和 Agent 运行日志留下可解释的跳过原因。

### 4.2 非目标

- 不删除 `github_repo_trends` 来源。
- 不在 P1 做完整的语义向量去重。
- 不在 P1 引入 Redis、队列、对象存储或新的调度系统。
- 不让前端用标题相似度临时隐藏重复卡片。
- 不把 star 增长本身立即定义为可重复发布的新事件。
- 不恢复旧版 `EvidenceCard / EventCluster / Brief` 主链路。

## 5. 推荐方案

### 5.1 总体策略

推荐采用四层防线：

```text
第一层：候选构造前后识别趋势信号身份
第二层：进入 LLM selector 前做 GitHub 仓库冷却期过滤
第三层：对历史已发布重复事件做一次性首页隐藏
第四层：产品列表查询层对纯 GitHub repo trend 做非破坏性兜底去重
```

前两层防止未来继续重复发布，第三层用于在用户明确授权后治理真实历史数据，第四层用于在尚未执行 `--apply` 前确保 `GET /events` 不继续把同 repo 纯趋势卡片重复展示给用户。

### 5.2 冷却期规则

默认规则：

```text
github_repo_trend_cooldown_days = 7
```

当一个 candidate group 满足以下条件时，应被判定为“近期重复趋势信号”：

- group 的来源全部是 `github_repo_trends`。
- 能从 signal metadata、source_item_id 或 GitHub URL 中解析出同一个 `owner/repo`。
- 该 repo 在最近 7 天内已经存在 `status = published` 的 PublishedEvent。
- 当前 group 没有 GitHub Release、官方公告、HN 高热讨论等强新鲜度信号。

命中后：

- 不进入 LLM Editorial Selector。
- 不生成 EventCandidate。
- 不生成 EventDossier。
- 不生成 PublishedEvent。
- 将相关 SourceSignal 标记为 `skipped_duplicate_trend`。
- 在 `metadata_json` 中记录跳过原因、匹配到的历史 PublishedEvent ID、跳过时间和冷却天数。

### 5.3 强新鲜度证据豁免

如果同一个 repo 的 group 包含以下任一来源，则不按纯趋势冷却处理：

- `github_releases`
- `hn_algolia`
- `openai_news`
- `anthropic_news`
- `nvidia_news`
- `deepmind_blog`
- `google_ai_blog`
- `huggingface_blog`
- `pytorch_blog`
- `ollama_blog`
- `aws_machine_learning_blog`

原因是这些来源更接近“发生了一件新事”，而不是“仓库仍然热门”。

注意：这不代表一定发布，只代表允许进入 selector。是否值得发仍由排序、selector 和审稿链路决定。

### 5.4 Star 增长如何处理

P1 不把 star 增长自动作为绕过冷却期的理由。

原因：

- 当前 star delta 只来自相邻快照，容易受采集间隔影响。
- 高 star 项目天然会反复出现，直接按 delta 放行会继续刷屏。
- 用户真正关心的是“发生了什么新事”，不是“这个老项目又涨了一点 star”。

P1 中 star 增长只作为排序和热度说明使用。后续如果要升级，可以单独设计“异常增长事件”，例如：

```text
24 小时 star 增长超过绝对阈值
且增长率超过相对阈值
且最近 14 天未发过同类 momentum update
```

这个后置，不进入本次修复。

## 6. 工程设计

### 6.1 新增趋势新鲜度服务

建议新增服务：

```text
apps/worker/worker/services/github_trend_freshness_service.py
```

职责：

- 判断一个 `EditorialCandidateGroup` 是否是纯 GitHub repo trend。
- 从 group 关联的 SourceSignal 中解析 `repo_full_name`。
- 查询最近 7 天是否已有同 repo PublishedEvent。
- 返回可解释的 allow / skip 结果。

建议返回结构：

```python
GitHubTrendFreshnessDecision(
    action="allow" | "skip",
    reason="first_seen_repo" | "has_hard_freshness_source" | "recently_published_repo_trend",
    repo_full_name="nousresearch/hermes-agent",
    matched_published_event_id="pub_xxx" | None,
    cooldown_days=7,
)
```

### 6.2 接入 DailyPipelineService

推荐接入点：

```text
DailyPipelineService._run_once_impl()
  -> build_candidate_groups_from_signal_rows()
  -> apply GitHub trend freshness gate
  -> select_candidate_groups()
```

也就是说，重复趋势 group 应该在进入 LLM selector 之前被工程代码过滤掉。

这样做的好处：

- 少花 LLM token。
- 规则稳定、可测试。
- selector 不需要背负“历史查重”的职责。
- 日志里能明确看到跳过原因。

### 6.3 SourceSignal 状态处理

现有 `SourceSignal` 已有 `status` 字段，可以复用，不需要 migration。

推荐状态：

```text
new
skipped_duplicate_trend
```

当 group 被冷却期规则跳过时，对关联 signals 做如下更新：

```text
SourceSignal.status = "skipped_duplicate_trend"
SourceSignal.metadata_json.github_trend_freshness = {
  "decision": "skip",
  "reason": "recently_published_repo_trend",
  "repo_full_name": "nousresearch/hermes-agent",
  "matched_published_event_id": "pub_xxx",
  "cooldown_days": 7,
  "skipped_at": "2026-06-26T..."
}
```

后续候选构造应默认只处理 `status = "new"` 且 `pipeline_run_id is null` 的 signal。

### 6.4 历史 PublishedEvent 匹配方式

P1 不新增字段，先通过现有关联链路查找同 repo 历史事件：

```text
PublishedEvent
-> EventCandidate
-> EventCandidateSignal
-> SourceSignal
-> metadata.full_name / source_item_id / canonical_url
```

匹配规则：

- 优先用 `SourceSignal.metadata_json.full_name`。
- 其次用 `SourceSignal.source_item_id`。
- 最后从 `canonical_url` 或 `original_url` 中解析 `github.com/{owner}/{repo}`。

匹配时统一小写：

```text
NousResearch/hermes-agent -> nousresearch/hermes-agent
```

### 6.5 已有重复事件治理

仅修未来链路不足以解决当前页面上已经出现的重复卡片。因此需要一次性治理脚本。

建议新增脚本：

```text
apps/worker/scripts/cleanup_duplicate_github_trend_events.py
```

默认 dry-run，只输出将要隐藏的事件；传 `--apply` 才真正更新。

治理规则：

- 按 repo_full_name 分组。
- 只处理主要由 `github_repo_trends` 产生的 PublishedEvent。
- 7 天内同 repo 出现多条 published event 时，只保留最新一条。
- 其余旧重复事件设置：

```text
PublishedEvent.status = "hidden_duplicate"
```

不物理删除，详情页是否仍可访问后续再讨论。P1 至少保证首页 `GET /events` 不再展示这些旧重复卡片，因为当前列表只返回 `status = published`。

### 6.6 产品列表查询兜底

在未获得用户授权执行 `--apply` 前，真实数据库里的历史重复事件仍然会保持 `published` 状态。为了让首页立即符合“同 repo 纯 GitHub trend 不刷屏”的产品口径，`ProductQueryService.list_published_events()` 需要在返回前做一层非破坏性去重：

- 只处理 `source_refs` 全部为 `source_key = github_repo_trends` 的事件。
- 从 `source_refs.url` 或 `source_refs.title` 解析 `owner/repo`。
- 按当前首页排序结果保留每个 repo 的第一条纯 trend 事件。
- GitHub Release、HN、官方公告等强新鲜度事件不参与这一层隐藏。
- 详情页 `GET /events/{slug}` 不受影响，历史事件仍可按 slug 访问。

这不是替代 cleanup 脚本，而是为了让真实首页在 cleanup apply 前也不继续展示重复趋势卡片。

## 7. 日志与可观测性

这次修复必须给后续“强力日志系统”留接口。

第一版至少需要在 summary 或日志中体现：

- `github_trend_groups_total`
- `github_trend_groups_skipped`
- `github_trend_groups_allowed`
- `skipped_duplicate_trend_signals`
- 被跳过 repo 的样例，例如 `nousresearch/hermes-agent`
- 匹配到的历史 `published_event_id`

如果当前运行日志基座已经合入，则使用 RunLogger 输出中文日志：

```text
GitHub 趋势去重：跳过 nousresearch/hermes-agent，原因：7 天内已发布过同仓库事件
```

如果日志基座还未稳定，则先把这些字段放入 daily pipeline summary，避免阻塞本次修复。

## 8. 数据流

修复后的主链路如下：

```text
collect_source_signals.py
  -> 写入 SourceSignal
  -> github_repo_trends 仍记录 detected_at、snapshot_bucket、star metrics

DailyPipelineService
  -> 读取本轮新 SourceSignal
  -> 构造 EditorialCandidateGroup
  -> GitHubTrendFreshnessService 过滤纯趋势重复 group
  -> 标记 skipped_duplicate_trend
  -> 其余 group 进入 LLM Editorial Selector
  -> run_event_pipeline
  -> PublishedEvent
```

首页读取仍保持：

```text
GET /events
  -> ProductQueryService.list_published_events()
  -> status = published
  -> homepage_rank / ranking_score / published_at 排序
```

## 9. 测试策略

本次必须测试先行。

### 9.1 服务级测试

新增或修改：

```text
apps/worker/tests/test_github_trend_freshness_service.py
```

覆盖：

- 首次出现的 repo trend 可以进入 selector。
- 7 天内已发布过的同 repo 纯 trend group 会被 skip。
- 超过 7 天的同 repo trend 可以再次进入 selector。
- group 含 `github_releases` 时，即使同 repo 近期发过 trend，也允许进入 selector。
- repo 匹配大小写不敏感。

### 9.2 DailyPipelineService 测试

修改：

```text
apps/worker/tests/test_daily_pipeline_service.py
```

覆盖：

- 本轮采集到重复 repo trend 时，不调用 selector 或不把该 group 传给 selector。
- summary 中包含 skipped 统计。
- 相关 SourceSignal 被标记为 `skipped_duplicate_trend`。

### 9.3 候选构造测试

修改：

```text
apps/worker/tests/test_editorial_candidate_service.py
```

覆盖：

- `status = skipped_duplicate_trend` 的 signal 不进入候选池。

### 9.4 数据治理脚本测试

新增：

```text
apps/worker/tests/test_cleanup_duplicate_github_trend_events.py
```

覆盖：

- dry-run 不修改数据库。
- `--apply` 隐藏同 repo 7 天内较旧的重复 trend events。
- 非 GitHub trend 事件不被误隐藏。
- 不同 repo 不互相影响。

## 10. 验收标准

修复完成后，至少满足：

- 同一个 GitHub repo 在 7 天内只有一条纯 trend PublishedEvent 能展示在首页。
- `hermes-agent` 这类已经发布过的 repo trend 再次被采集时，不再生成新 PublishedEvent。
- 如果同 repo 后续出现 GitHub Release 或官方公告，仍可进入候选和 selector。
- 首页不再展示当前数据库中的多条 Hermes-agent 重复卡片。
- 测试中能看到 RED -> GREEN 过程记录。
- 后端测试记录文档写明测了什么、输入是什么、结果是什么。
- 不修改前端排序逻辑。
- 不提交 `.env`、runtime 日志、Next 自动生成文件或无关观测系统改动。

## 11. 方案对比

### 方案 A：只在前端隐藏重复卡片

优点：最快。

缺点：后端仍然持续生产重复事件，LLM token 继续浪费，数据库越来越脏，后台审计也会混乱。

结论：不采用。

### 方案 B：工程冷却期过滤 + 一次性数据治理

优点：稳定、可测试、成本低，不推翻现有链路，能同时解决未来重复和当前首页重复。

缺点：规则相对保守，某些高热老仓库短期内不会反复出现在首页。

结论：采用。

### 方案 C：语义向量去重 + Agent 判断是否重复

优点：长期更智能，可处理标题不同但主题相同的复杂事件。

缺点：需要 embedding、向量库或额外 LLM 判断，成本和不确定性都更高，P1 不适合。

结论：后续升级方向，不进入本次修复。

## 12. 待后续升级

本次修复后，后续可以继续增强：

- 给 `PublishedEvent` 增加稳定的 `event_identity_key`。
- 给 repo trend 增加专门的 `trend_kind` 和 `event_time_kind` 字段。
- 设计“异常增长事件”规则，而不是简单按 star delta 放行。
- 引入 embedding 做跨来源语义去重。
- 后台管理页支持手动合并重复事件、隐藏事件、解除隐藏。
- 将趋势信号以“观察池”形式展示，而不是全部进入首页事件流。

## 13. 最终口径

P1 的最终口径是：

> GitHub repo trends 负责发现“哪些仓库正在被关注”，但首页 PublishedEvent 负责展示“哪些事情值得现在发给用户看”。同一仓库短期反复出现在热榜，不等于每天都发生了一件新事。

因此，本次修复必须把 `github_repo_trends` 从“可直接反复发布的事件源”降级为“需要冷却期和新鲜度判断的趋势信号源”。
