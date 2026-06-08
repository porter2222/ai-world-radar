# AI 事件重要性与热议度采集策略报告

更新时间：2026-06-05

## 1. 报告目的

用户提出的问题不是“怎样抓最火的内容”，而是：

> AI World Radar 到底需要抓哪些信息，怎样同时发现“最热议”和“最重要”的 AI 事件。

本报告基于项目已有 docs 的产品定义、信息源策略、Agent 系统设计、数据模型设计，以及已有 GitHub 采集策略调研，重新整理一套适合 AI World Radar 的采集与排序策略。

重点回答：

- 系统应该采集什么，而不是只看什么最火。
- 什么内容应进入事件生产链路。
- 什么内容只是线索，什么内容应该丢弃。
- 怎样用工程规则和 Agent 判断结合，筛出“值得中文 AI 学习型用户关注”的事件。
- 哪些开源项目的源码策略可借鉴到 P1、P1.5、P2。

## 2. 从项目 docs 抽出的核心信息需求

AI World Radar 的核心内容单位不是新闻、帖子、视频、仓库或网页，而是：

> AI 事件。

项目文档中对事件的要求可以压缩成一句话：

> 最近一段时间内，AI 圈发生或正在形成讨论的、具备明确主体、明确变化、可追溯来源，并且对中文 AI 学习型用户有认知价值的信息单元。

候选事件必须能说成：

> 谁或什么东西，发生了什么变化。

因此，采集系统的目标不是“抓更多链接”，而是发现并支撑以下信息：

| 目标信息 | 含义 | 示例 |
|---|---|---|
| 主体 | 事件围绕谁或什么 | OpenAI、Claude、Gemini、GitHub Copilot、某个开源仓库、某篇论文 |
| 触发点 | 发生了什么变化 | 发布、更新、涨价、下架、开源、爆火、争议、政策变化 |
| 时间性 | 何时发生或何时开始发酵 | 发布时间、首次发现时间、热议窗口 |
| 来源 | 从哪里来，能否回源 | 官方博客、GitHub、HN、HF、YouTube、Reddit、聚合源 |
| 热度线索 | 是否正在被讨论 | 排名、评论数、增速、多平台重复出现 |
| 重要度线索 | 即使不热也值得关注的理由 | 权威主体、重大模型、核心论文、开发者生态影响、安全政策 |
| 中文用户价值 | 为什么中文 AI 学习型用户需要知道 | 学习认知、工具使用、行业理解、开发实践、风险理解 |

## 3. AI World Radar 不应该只追“火爆”

只追热门会出现三个问题：

- 娱乐化：热点争议、标题党、搬运号会盖过真正重要的模型、论文和基础设施变化。
- 漏掉低热高影响事件：官方发布、API 价格变化、开发者平台更新、政策文件，刚发布时未必高热。
- 重复污染：同一事件被 HN、X、YouTube、中文站和 newsletter 重复传播，如果不聚合，会变成多条重复新闻。

项目 docs 已经给出排序口径：

> 热度主导 + 重要度兜底 + 中文用户价值修正。

所以采集和排序需要同时跑两条线：

| 线索类型 | 目标 | 典型来源 | 最终去向 |
|---|---|---|---|
| 热议线 | 找正在发酵的讨论 | HN、GitHub Trending、HF Trending、Reddit、YouTube、X | 热议型候选事件 |
| 重要线 | 找影响大但未必爆火的事件 | 官方博客、GitHub Changelog、重要仓库、论文、政策、安全公告 | 事实型候选事件 |

## 4. 四档分流模型

采集到的原始条目进入系统后，不应该直接交给写作 Agent，而应先进入四档分流。

### 4.1 事实型候选事件

已有明确事实发生，可以进入事件生成链路。

典型例子：

- 官方发布新模型。
- 产品上线新功能。
- GitHub 仓库发布 release。
- Hugging Face 出现重要模型。
- 公司发布公告。
- 论文或报告发布。

识别策略：

- 来源是官方、一手页面、GitHub、HF、论文页、产品发布页。
- 标题或正文包含明确事件动词：发布、上线、更新、开源、弃用、涨价、合并、收购、监管、漏洞。
- 能抽取出主体 + 触发点 + 时间。

### 4.2 热议型候选事件

外网讨论热度很高，能反映趋势、争议或舆论变化。它不一定是已确认事实，但“正在被讨论”本身可以成为事件。

典型例子：

- HN 高位讨论某 AI coding 工具变化。
- Reddit 多个指定社区集中讨论某模型表现。
- YouTube 多个已知 AI 频道同一天讲同一产品。
- GitHub 某 AI 项目突然进入 Trending。

表达原则：

- 已确认的是“讨论正在发生”。
- 未确认的是讨论里的具体说法。
- 发布时应谨慎写成“社区热议”“尚未看到官方确认”“仍需观察”。

### 4.3 待核验线索

暂时不适合公开发布，但值得继续观察。

进入条件：

- 只有一个聚合源提到，尚未找到一手来源。
- 只有单个平台讨论，热度还不够高。
- 主体明确，但变化不清楚。
- 传闻有扩散迹象，但缺少可靠来源。
- 事件可能重要，但当前信息太少。
- 疑似旧闻翻新，需要确认时间。

处理策略：

- 不上首页。
- 不进今日简报。
- 不生成详情页。
- 继续补源、补热度、补时间线。

### 4.4 丢弃内容

不具备事件价值、来源价值或用户认知价值。

直接丢弃：

- 普通教程。
- 工具合集。
- 明显营销软文。
- 无来源搬运。
- 主体不清。
- 旧闻重复。
- AI 相关性弱的泛科技新闻。
- 纯投资或股价短讯。

例外：

如果教程、观点文章或工具合集本身形成高热讨论，可以作为“热议型事件”入池。此时事件不是教程内容，而是“该内容引发了外网热议”。

## 5. 采集目标分层

AI World Radar 的来源应分成三层。

| 来源层 | 作用 | P1 是否适合 | 示例 |
|---|---|---|---|
| 事实源 | 支撑正式事件 | 适合 | OpenAI News、Anthropic News、DeepMind Blog、NVIDIA Blog、GitHub Changelog、论文页 |
| 热度源 | 判断外网是否关注 | P1 简单源，P1.5 扩展 | HN、GitHub Trending、HF Trending、Reddit、YouTube、X |
| 线索源 | 补盲和冷启动 | 可用但不能当唯一事实依据 | TLDR AI、AIBase、newsletter、竞品聚合站 |

P1 不需要追求全网覆盖。P1 应优先跑通：

```text
稳定来源采集
-> EvidenceCard
-> EventCluster
-> Ranking
-> Detail / Brief
-> Quality Gate
-> PublishedEvent
```

## 6. 热度算法

热度不是单纯的点赞数或评论数，因为不同平台尺度不同。AI World Radar 更适合使用“多维热度信号”。

### 6.1 平台位置分

平台把内容放到什么位置，本身就是强信号。

| 平台 | 可用位置 | 评分建议 |
|---|---|---|
| Hacker News | topstories / beststories / item rank | 排名越靠前越高 |
| GitHub Trending | daily / weekly rank | daily rank 优先，weekly 做持续热度 |
| Hugging Face | trending_score / likes / downloads | trending_score 和最近修改优先 |
| Reddit | hot / rising / top | rising 抓爆发，top 抓已验证热度 |
| YouTube | 频道新视频、搜索排序、播放/评论 | 先频道白名单，再看统计增量 |

示例公式：

```text
platform_rank_score = 1 - (rank - 1) / max_rank
```

如果某条 HN story 在 Top 30，rank 越靠前，分越高。超过 Top 100 可以只作为普通候选。

### 6.2 互动强度分

互动强度用于衡量“人们是否真的在讨论”。

常见字段：

- HN：score、descendants。
- Reddit：score、num_comments、upvote_ratio。
- YouTube：viewCount、likeCount、commentCount。
- GitHub：stars、forks、stars today。
- HF：likes、downloads、trending_score。

建议对绝对数做 `log1p`，避免大平台数字碾压小平台：

```text
engagement_score = log1p(weighted_likes + 2 * comments + 3 * shares)
```

### 6.3 增长速度分

比总量更重要的是增长速度。

```text
velocity = (current_metric - previous_metric) / hours_since_last_seen
```

适合发现：

- 刚进入 GitHub Trending 的仓库。
- HN 评论迅速增长的 story。
- YouTube 新视频评论暴增。
- Reddit rising 里快速冒头的帖子。

### 6.4 爆发检测

用于发现“平时不高，但突然异常高”的事件。

简单可落地做法：

```text
burst_score = (current_velocity - source_baseline_velocity) / source_std
```

P1 可以先不做复杂统计，只保存每轮指标。P1.5 再引入 source 级 baseline。

### 6.5 跨源共振分

同一事件在多个来源出现，比单一平台更可靠。

```text
cross_source_score = log1p(distinct_source_count) + platform_diversity_bonus
```

例如：

- OpenAI 官方发布 + HN 高位讨论 + TLDR AI 提及。
- 某 GitHub repo Trending + HF model 页面 + Reddit 讨论。

这类事件应优先进入 EventCluster。

### 6.6 讨论质量分

高互动不一定是高质量。需要惩罚低质噪声。

正向信号：

- 评论集中讨论技术、产品变化、使用体验。
- 有高质量外链、代码、论文、benchmark。
- 多个可信账号或社区成员参与。

负向信号：

- 纯情绪化争吵。
- 大量重复转发。
- 标题党。
- 抽奖、优惠、营销。
- 与 AI 事件无关的泛讨论。

P1 可由 Agent 在 EvidenceCard 中输出 `heat_clues` 和 `candidate_reason`，不必复杂建模。

## 7. 重要度算法

重要度用于兜底“低热但必须知道”的事件。

### 7.1 主体重要度

主体越关键，越需要兜底。

高权重主体：

- Frontier lab：OpenAI、Anthropic、Google DeepMind。
- AI 基础设施：NVIDIA、GitHub、Microsoft、Meta、Google、Hugging Face。
- 重要开发者工具：Cursor、Windsurf、Claude Code、GitHub Copilot、MCP 生态。
- 重要开源项目：transformers、vLLM、llama.cpp、Ollama、LangChain、LlamaIndex、ComfyUI 等。

示例：

```yaml
subject_tier:
  frontier_lab: 1.00
  ai_infra_platform: 0.90
  major_dev_tool: 0.85
  major_open_source: 0.80
  normal_project: 0.45
```

### 7.2 事件类型重要度

不同事件类型的默认重要性不同。

| 事件类型 | 默认重要度 | 说明 |
|---|---:|---|
| 模型发布 | 高 | 直接影响 AI 圈认知 |
| API / 价格 / 平台能力变化 | 高 | 影响开发者和产品使用 |
| 安全、政策、版权、监管 | 高 | 影响长期风险和行业走向 |
| 重要开源项目发布 | 中高 | 影响实践路径 |
| 核心论文 / benchmark | 中高 | 影响研究与技术理解 |
| 公司合作 / 生态变化 | 中 | 需要看主体和范围 |
| 普通产品小功能 | 中低 | 除非热度很高 |
| 观点文章 | 低到中 | 除非形成高质量讨论 |
| 工具合集 / 教程 | 默认低 | 除非自身成为热议事件 |

### 7.3 来源质量分

注意：最新技术口径里，P1 不做真实性评分，也不做“官方确认状态”字段。因此这里不建议叫 `truth_score` 或 `credibility_score`，而应使用更工程化的：

- source quality。
- source level。
- source type。
- impact signal weight。

建议：

```yaml
source_quality:
  official: 1.00
  first_party_platform: 0.90
  research_paper: 0.85
  developer_platform: 0.80
  community: 0.55
  newsletter: 0.45
  competitor: 0.35
```

来源质量不代表事实核验完成，只代表“作为事件线索或证据的优先级”。

### 7.4 影响范围分

影响范围判断这个事件会影响谁。

高影响范围：

- 大量普通用户。
- 开发者和 API 使用者。
- 研究者。
- 开源生态。
- 企业采购和部署。
- 政策、版权、安全合规。

低影响范围：

- 单一小工具更新。
- 单一作者观点。
- 单一地区弱相关资讯。
- 与 AI 相关性弱的泛科技新闻。

### 7.5 新颖性与认知价值

对中文 AI 学习型用户来说，重要的信息不只是“发生了”，还要能帮助建立认知。

加分项：

- 新能力：出现新的模型能力、产品形态或开发模式。
- 新约束：价格、政策、API 限制、安全风险变化。
- 新生态：开源工具、协议、平台能力改变实践方式。
- 新争议：社区对某个趋势形成明显分歧。

## 8. 推荐综合排序模型

项目当前口径是：

```text
热度主导 + 重要度兜底 + 中文用户价值修正
```

建议落地成两阶段。

### 8.1 第一阶段：候选入池

先判断是否值得进入候选池。

```text
入池条件 =
  事实型强信号
  OR 热议型强信号
  OR 两个中等信号
  OR 高重要度兜底
```

强信号：

- 官方或一手来源出现明确事件。
- HN 高位讨论。
- GitHub Trending 排名靠前。
- HF Trending / Papers 排名靠前。
- 指定社区高互动讨论。
- 重要主体引发集中讨论。

中等信号：

- 多个线索源重复提及同一事件。
- 同一项目同时出现在 GitHub、HN、HF、newsletter。
- 指标增长明显但尚未形成强榜单信号。
- 聚合源和社区讨论同时出现。

### 8.2 第二阶段：EventCluster 排名

建议初版公式：

```text
ranking_score =
  0.40 * heat_score
  + 0.30 * impact_score
  + 0.20 * audience_value_score
  + 0.10 * freshness_score
  + evidence_bonus
  - risk_penalty
```

同时增加两个硬规则：

```text
if impact_score >= 0.85 and source_quality >= 0.80:
    publish_decision = publish_or_hold_for_content
```

```text
if heat_score >= 0.80 and source_quality < 0.50:
    publish_decision = hot_discussion_or_hold
    writing_style = cautious
```

这样可以避免两个极端：

- 低热但重要的官方事件被漏掉。
- 很热但来源差的传闻被写成确定事实。

### 8.3 三个核心分数

#### heat_score

```text
heat_score =
  0.30 * platform_rank_score
  + 0.25 * engagement_score
  + 0.20 * velocity_score
  + 0.15 * cross_source_score
  + 0.10 * discussion_quality_score
```

#### impact_score

```text
impact_score =
  0.30 * subject_tier_score
  + 0.25 * event_type_score
  + 0.20 * source_quality_score
  + 0.15 * scope_score
  + 0.10 * novelty_score
```

#### audience_value_score

```text
audience_value_score =
  learning_value
  + developer_relevance
  + product_user_relevance
  + chinese_context_relevance
  + explainability
```

P1 可以先让 RankingAgent 输出 0-1 的结构化评分和理由；工程代码保留最终排序控制权。

## 9. 采集策略与开源项目参考

### 9.1 固定事实源：RSS / API / 官方页面

适合 P1。

参考项目：

- feedparser：https://github.com/kurtmckee/feedparser
- RSSHub：https://github.com/DIYgod/RSSHub
- Miniflux：https://github.com/miniflux/v2

可借鉴策略：

- 使用固定 source registry，而不是临时搜索。
- 每个 source 有固定 adapter。
- 使用 `etag`、`last_modified`、`guid`、`canonical_url`、`published_at` 做增量和去重。
- 解析失败要记录 source health。

AI World Radar 落地：

- OpenAI News、Anthropic News、DeepMind Blog、NVIDIA Blog、GitHub Changelog 先走这条路。
- 这类来源主要贡献 `impact_score` 和事实型候选事件。

### 9.2 HN：工程师圈热议发现

参考项目：

- Hacker News API：https://github.com/HackerNews/API
- node-hnapi：https://github.com/cheeaun/node-hnapi

可借鉴策略：

- 先从 topstories/newstories/beststories 拿 ID。
- 再查 item detail。
- 通过 score、descendants、time 判断热度。
- 用 URL、item id、title 合并重复。

AI World Radar 落地：

- P1 第一功能切片就是 HN AI 事件生产闭环。
- HN 既能贡献热度，也能贡献开发者视角的讨论焦点。
- HN 不直接证明事实，只作为社区热议和技术圈关注信号。

### 9.3 GitHub：开源项目与开发者生态

参考项目：

- github-trending-api：https://github.com/huchenme/github-trending-api
- go-trending：https://github.com/andygrunwald/go-trending
- github-trending-repos：https://github.com/vitalets/github-trending-repos
- agents-radar：https://github.com/duanyytop/agents-radar

可借鉴策略：

- GitHub Trending 是榜单采样，不是事实源。
- GitHub API / Changelog / Release 更适合事实型事件。
- Trending 每日快照可用于发现未知开源项目。
- repo full_name 是稳定去重 key。

AI World Radar 落地：

- P1 先做 GitHub Changelog、重点 repo watchlist。
- P1.5 再做 GitHub Trending 每日快照。
- 热度看 stars today、rank、重复出现在 HN/HF/Reddit 的情况。

### 9.4 Hugging Face：模型、论文和社区热度

参考项目：

- huggingface_hub：https://github.com/huggingface/huggingface_hub
- RSSHub：https://github.com/DIYgod/RSSHub

可借鉴策略：

- 用官方 API 的 sort/filter/search。
- 关注 `downloads`、`likes`、`last_modified`、`trending_score`。
- repo_id / paper id 作为去重 key。

AI World Radar 落地：

- P1 可接 Models / Papers / Trending。
- HF 适合发现模型社区和论文热度。
- 对新模型只写“社区关注”不够，还要补模型卡、论文或作者发布页。

### 9.5 Reddit：指定社区热议

参考项目：

- PRAW：https://github.com/praw-dev/praw
- prawcore：https://github.com/praw-dev/prawcore
- asyncpraw：https://github.com/praw-dev/asyncpraw

可借鉴策略：

- subreddit whitelist，而不是全站搜索。
- 使用 hot/top/rising/search。
- 使用 `time_filter=hour/day/week`。
- 使用 score、num_comments、upvote_ratio、created_utc。
- prawcore 处理 rate limit headers。

AI World Radar 落地：

- P1 不做 Reddit。
- P1.5 可监听 `r/MachineLearning`、`r/LocalLLaMA`、`r/OpenAI` 等。
- Reddit 是热议源，不是事实源。

### 9.6 YouTube：视频与解释型热度

参考项目：

- youtube/api-samples：https://github.com/youtube/api-samples
- google-api-python-client：https://github.com/googleapis/google-api-python-client
- youtube-transcript-api：https://github.com/jdepoix/youtube-transcript-api
- youtube-comment-downloader：https://github.com/egbertbouman/youtube-comment-downloader
- yt-dlp：https://github.com/yt-dlp/yt-dlp

可借鉴策略：

- 先维护频道白名单。
- 用 `publishedAfter` 拉近期视频。
- 用 `videos.list` 补 views、likes、comments。
- 字幕和评论只对入选视频做 enrichment。

AI World Radar 落地：

- P1 不做广域 YouTube。
- P1.5 可接已知 AI 频道。
- P2 再做字幕/评论增强。

### 9.7 变更监控：无 RSS 页面兜底

参考项目：

- changedetection.io：https://github.com/dgtlmoon/changedetection.io
- Huginn：https://github.com/huginn/huginn

可借鉴策略：

- 对少量高价值页面做 snapshot。
- 新旧内容 diff 后再进入 parser。
- 每个 watch 有 expected update period、last error 和 selector。

AI World Radar 落地：

- 用于少量没有 RSS/API 的官方页面。
- 不做广域网页爬虫。

### 9.8 社媒高风险项目：只借鉴架构

参考项目：

- Tweepy：https://github.com/tweepy/tweepy
- twarc：https://github.com/DocNow/twarc
- MediaCrawler：https://github.com/NanmiCoder/MediaCrawler
- Crawlee：https://github.com/apify/crawlee
- Scrapy：https://github.com/scrapy/scrapy
- Crawl4AI：https://github.com/unclecode/crawl4ai

可借鉴策略：

- search / detail / creator 三入口。
- request queue。
- cursor / pagination。
- source health。
- retry。
- snapshot。
- 采集上限。
- adapter 分层。

不建议：

- cookie 登录。
- 账号池。
- 代理池绕风控。
- 私有 GraphQL。
- 抓取私密内容。
- 把高风险 scraper 放进 P1 自动发布链路。

## 10. 推荐 P1 实现顺序

### 10.1 P1 第一切片：HN AI 事件生产闭环

目标不是做完所有采集，而是跑通完整事件生产链。

```text
HN API
-> SourceItem
-> EvidenceCard
-> EventCluster
-> Ranking
-> Detail / Brief
-> Quality Gate
-> PublishedEvent
```

HN 的好处：

- API 简单。
- 有热度字段。
- 有标题、URL、评论数。
- 适合训练“热议型事件”判断。

### 10.2 P1 第二切片：官方事实源

接入：

- OpenAI News。
- Anthropic News。
- Google DeepMind Blog。
- NVIDIA Blog/RSS。
- GitHub Changelog。

目标：

- 训练“重要但未必热”的兜底策略。
- 让系统能发布事实型事件。

### 10.3 P1 第三切片：GitHub / Hugging Face

接入：

- GitHub Changelog / Releases / watchlist。
- Hugging Face Models / Papers / Trending。

目标：

- 覆盖开源项目、模型社区、论文热度。
- 验证 repo_id / paper_id / canonical_url 去重。

### 10.4 P1.5：热度增强

接入：

- GitHub Trending 每日快照。
- Reddit 指定社区。
- YouTube 指定频道。
- HN Algolia query profile。
- 少量 changedetection watch。

目标：

- 增加早期发现。
- 增加跨平台共振。
- 增加互动增速和爆发检测。

### 10.5 P2：高风险和深度增强

可考虑：

- X 官方 API。
- YouTube transcript / comment enrichment。
- Facebook Graph API 授权页面。
- 中文社媒授权实验。
- Browser fallback。

仍然不建议：

- 非官方 cookie 登录采集。
- 账号池和代理池。
- 私密内容采集。
- 把社媒传闻直接写成事实。

## 11. 推荐字段补充

当前数据模型已经有 `heat_score`、`impact_score`、`audience_value_score`、`ranking_score`，建议开发时进一步明确这些字段的来源。

### 11.1 EvidenceCard 级字段

```yaml
raw_heat_metrics:
  platform_rank: 12
  score: 180
  comments: 75
  likes: null
  views: null
  stars_today: null
  downloads: null

heat_clues:
  - HN topstories rank 12
  - 75 comments in engineering discussion

impact_clues:
  - official source mentions API capability change
  - affects developer workflow

suggested_route: high_heat_candidate
candidate_score: 0.78
candidate_reason: HN high discussion plus AI developer relevance
```

### 11.2 EventCluster 级字段

```yaml
heat_score: 0.82
impact_score: 0.74
audience_value_score: 0.88
ranking_score: 0.81
ranking_reason: High HN discussion, developer relevance, and official source attached.
publish_decision: publish
brief_candidate: true
```

## 12. 推荐 Query Profile

关键词不应该由 Agent 临时自由发挥，应配置成可审计的 query profile。

```yaml
query_profile:
  id: ai_world_radar_core_en
  purpose: discover AI events, not generic AI content
  entities:
    - OpenAI
    - ChatGPT
    - Anthropic
    - Claude
    - Gemini
    - DeepMind
    - NVIDIA
    - GitHub Copilot
    - Cursor
    - Hugging Face
  event_terms:
    - launch
    - release
    - announce
    - update
    - API
    - pricing
    - open source
    - benchmark
    - safety
    - policy
    - lawsuit
    - outage
    - acquisition
  negative_terms:
    - coupon
    - giveaway
    - tutorial
    - prompt pack
    - hiring
    - meme
  time_window_hours: 24
  max_pages: 3
```

## 13. 推荐分流规则

```text
if not ai_related:
    route = discarded

elif has_subject and has_trigger and source_type in official_or_first_party:
    route = fact_candidate

elif heat_score >= strong_heat_threshold:
    route = high_heat_candidate

elif impact_score >= high_impact_threshold:
    route = high_impact_candidate

elif has_two_medium_signals:
    route = normal_candidate

elif subject_clear_but_source_insufficient:
    route = watchlist_lead

else:
    route = discarded
```

## 14. 推荐去重与聚合规则

事件合并以：

```text
主体 + 触发点 + 时间窗口
```

为核心。

优先级：

1. 稳定平台 ID：HN item id、GitHub repo full_name、HF repo_id、YouTube videoId。
2. canonical URL。
3. content hash。
4. normalized title + subject + event_trigger。
5. Agent 辅助判断。

合并规则：

- 同一主体 + 同一触发点：合并。
- 同一主体 + 不同触发点：拆分。
- 社区讨论依附事实事件：合并到事实事件。
- 社区讨论本身成为焦点：单独形成热议型事件。
- 后续发展优先更新原事件，只有实质新变化才拆新事件。

## 15. 推荐质量门禁

发布前至少检查：

- 有可点击来源。
- 标题和正文一致。
- 未确认内容没有写成事实。
- 社区热议事件标明讨论性质。
- 详情页不是字段堆叠。
- 不直接搬运竞品正文。
- 不生成不存在的链接、截图、数据或人物言论。
- 内容不足时可以少发，不强行凑 Top 12。

## 16. 最终建议

AI World Radar 的采集系统应该围绕“事件价值”设计，而不是围绕“网页数量”设计。

推荐核心架构：

```text
Source Registry
-> Adapter Fetch
-> SourceItem
-> EvidenceCard
-> Four-way Route
-> EventCluster
-> Heat / Impact / Audience Ranking
-> Quality Gate
-> PublishedEvent / Brief
```

最重要的设计判断是：

> 热度负责发现正在发生的讨论，重要度负责防漏关键事件，中文用户价值负责决定它是否值得展示给目标用户。

P1 不要急着做全平台大爬虫。先用 HN、官方源、GitHub、Hugging Face 跑通“重要 + 热议”的完整判断链路，再把 Reddit、YouTube、X 等复杂平台作为 P1.5/P2 增强。

## 17. 参考项目与资料

- feedparser：https://github.com/kurtmckee/feedparser
- RSSHub：https://github.com/DIYgod/RSSHub
- Miniflux：https://github.com/miniflux/v2
- Huginn：https://github.com/huginn/huginn
- changedetection.io：https://github.com/dgtlmoon/changedetection.io
- Hacker News API：https://github.com/HackerNews/API
- node-hnapi：https://github.com/cheeaun/node-hnapi
- PRAW：https://github.com/praw-dev/praw
- prawcore：https://github.com/praw-dev/prawcore
- YouTube API Samples：https://github.com/youtube/api-samples
- Google API Python Client：https://github.com/googleapis/google-api-python-client
- Hugging Face Hub：https://github.com/huggingface/huggingface_hub
- GitHub Trending API：https://github.com/huchenme/github-trending-api
- go-trending：https://github.com/andygrunwald/go-trending
- github-trending-repos：https://github.com/vitalets/github-trending-repos
- agents-radar：https://github.com/duanyytop/agents-radar
- MediaCrawler：https://github.com/NanmiCoder/MediaCrawler
- Crawlee：https://github.com/apify/crawlee
- Scrapy：https://github.com/scrapy/scrapy
- Crawl4AI：https://github.com/unclecode/crawl4ai
