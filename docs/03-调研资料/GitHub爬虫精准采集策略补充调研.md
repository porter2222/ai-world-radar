# GitHub 爬虫精准采集策略补充调研

更新时间：2026-06-05

## 1. 调研目的

这份补充报告专门回答一个问题：AI World Radar 后续做采集系统时，如何更精准地爬到想要的信息，而不是只靠 `openai`、`cursor`、`claude` 这类关键词在全网粗暴搜索。

本报告基于 `GitHub采集策略调研.md` 已覆盖的开源仓库和本地源码观察，重点提炼仓库背后的采集策略：

- 入口怎么确定：RSS、API endpoint、账号、频道、subreddit、repo、榜单、页面 URL、内容 ID。
- 候选怎么召回：关键词、source watchlist、平台原生搜索、趋势榜、变更监控、已知 ID enrichment。
- 如何收敛：时间窗口、分页游标、排序、热度字段、白名单/黑名单、去重、证据等级。
- 哪些策略适合 AI World Radar P1、P1.5、P2。
- 哪些策略虽然“能爬”，但不应该进入生产链路。

关联已有报告：

- [GitHub采集策略调研.md](GitHub采集策略调研.md)
- [GitHub采集策略仓库清单.md](GitHub采集策略仓库清单.md)

## 2. 一句话结论

精准采集不是“给 Agent 几个关键词让它去爬”，而是“先锁定可信来源和平台入口，再用时间窗口、平台排序、结构化字段和二次语义过滤，把候选事件一步步收窄成可追溯证据”。

## 3. 关键词策略为什么不够

只把 `openai`、`cursor`、`claude` 设成关键词有用，但只能算最粗的召回层，问题很多：

- 噪声高：关键词会命中教程、吐槽、招聘、广告、旧闻、二次转载。
- 漏召回：很多事件不会直接写品牌词，例如 “new coding agent benchmark”、“frontier model price cut”。
- 无来源等级：关键词命中 Reddit 评论和官方博客，看起来都是一条结果，但可信度完全不同。
- 难去重：同一事件会被官方博客、HN、GitHub、YouTube、中文站重复报道。
- 不稳定：社媒搜索排序会变，平台搜索结果会个性化或漂移。
- 无法回答“为什么重要”：关键词只能发现命中，不能稳定判断热度、影响范围和证据链。

更合理的方式是把关键词放在一个多层策略中：

```text
固定信源入口
-> 平台原生检索/榜单/时间窗
-> 结构化字段抽取
-> 规则过滤与去重
-> 详情/评论/字幕/仓库数据补证
-> Agent 做语义判断和事件聚合
-> Evidence Card / Published Event
```

## 4. 精准采集策略菜单

### 4.1 固定可信源采集

适合 P1。

做法：

- 对 OpenAI News、Anthropic News、Google DeepMind Blog、NVIDIA Blog、GitHub Changelog 等维护固定 source registry。
- 每个 source 记录固定 entrypoint，例如 RSS URL、API URL、页面 URL。
- 不靠关键词发现源，只从这些稳定入口拉取新内容。
- 用 `etag`、`last_modified`、`guid`、`canonical_url`、`published_at` 做增量和去重。

参考仓库：

- `kurtmckee/feedparser`：RSS/Atom/JSON Feed 解析，支持 `etag`、`modified` 条件请求。
- `DIYgod/RSSHub`：用 route registry 把不同站点转成统一 RSS 输出。
- `miniflux/v2`：RSS reader 的 fetcher/parser/storage/worker 分层。

AI World Radar 建议：

- P1 第一批只做这种策略。
- Agent 不直接读网页决定事实，只处理已经规范化的 Raw Item / Evidence Card。
- 每条 raw item 必须保留 raw snapshot、source_id、parser_version、fetch_time。

### 4.2 Source Watchlist 策略

适合 P1/P1.5。

做法：

- 先维护一组高价值对象，而不是全网搜索：
  - 官方博客：OpenAI、Anthropic、DeepMind、NVIDIA。
  - GitHub org/repo：openai、anthropics、vercel、modelcontextprotocol、ollama、vllm、langchain-ai、huggingface。
  - Reddit subreddit：`r/MachineLearning`、`r/LocalLLaMA`、`r/OpenAI`、`r/singularity`。
  - YouTube channel：OpenAI、Anthropic、Google DeepMind、NVIDIA、AI Explained、Two Minute Papers 等。
  - X account/list：只在未来官方 API 预算允许时考虑。
- 对 watchlist 内对象做低频、稳定、可解释的增量采集。

优点：

- 噪声远低于全网关键词。
- 事件来源更可解释。
- 更容易做 source health、rate limit 和失败降级。

### 4.3 平台原生搜索策略

适合 P1.5。

做法：

- 使用平台自己的搜索 API 或搜索 endpoint，而不是自己扫网页。
- query 不只包含实体词，还要包含事件动词、技术词、产品词、排除词。
- 每个平台单独设计 query profile。

示例：

```yaml
query_profile:
  id: ai_model_release_en
  entities:
    - OpenAI
    - Claude
    - Anthropic
    - DeepMind
    - Gemini
    - Cursor
    - Windsurf
  event_terms:
    - launch
    - release
    - announce
    - API
    - pricing
    - benchmark
    - open source
  negative_terms:
    - giveaway
    - coupon
    - hiring
    - meme
  time_window_hours: 24
  max_pages: 3
```

注意：

- 关键词只负责召回候选，不负责最终判断。
- 对每个平台要记录 query、排序、时间窗、页数和 cursor。
- 同一个 query profile 的结果要可回放，不能让 Agent 每次自由发挥。

### 4.4 平台榜单/热榜策略

适合 P1/P1.5。

做法：

- 不是搜索关键词，而是直接读取平台提供的热点入口：
  - GitHub Trending。
  - Hacker News topstories/newstories。
  - Hugging Face trending models / papers。
  - Reddit subreddit top/hot。
  - YouTube channel popular/new videos。
- 先接受平台排序作为“热度候选”，再用 AI 领域规则过滤。

适用场景：

- 发现未知新项目。
- 发现突然爆火的开源仓库、模型、论文、讨论。
- 作为官方源之外的早期弱信号。

风险：

- 热不等于真。
- 榜单容易被短期传播、营销或社区偏好影响。
- GitHub Trending / 部分网页榜单没有官方 API，必须保存每日快照和 selector test。

### 4.5 已知 ID 详情补全策略

适合 P1/P1.5/P2。

做法：

- 先从列表页、搜索、RSS、API 拿到稳定 ID。
- 再用详情接口补字段。

典型 ID：

- X：tweet ID、user ID、list ID。
- Reddit：submission ID、comment ID、subreddit。
- YouTube：videoId、channelId、playlistId、comment id、caption id。
- GitHub：repo full_name、release id、issue/PR number、commit sha。
- Hugging Face：repo_id、paper id、space id。
- RSS：guid、canonical_url。

为什么重要：

- 列表页通常字段少、摘要短、排序会变。
- 详情接口能补正文、统计、作者、评论、字幕、关联链接。
- 去重也应优先使用稳定 ID，而不是标题相似度。

### 4.6 时间窗口与水位策略

适合所有阶段。

做法：

- 每个 source adapter 维护自己的水位：
  - RSS：`etag`、`last_modified`、最新 `published_at`。
  - Reddit：`after` cursor、`created_utc`、`time_filter`。
  - X 官方 API：`since_id`、`until_id`、`start_time`、`end_time`、`next_token`。
  - YouTube：`publishedAfter`、`publishedBefore`、`pageToken`。
  - HN Algolia：`created_at_i` numeric range。
  - GitHub API：`since`、`pushed`、`created`、`updated`。
- 采集任务只拉近窗口内数据，避免无限回扫。

建议：

- P1 默认 1 小时到 6 小时低频轮询。
- 趋势榜每日快照即可。
- 社区热源 P1.5 再做 1 小时级或 3 小时级窗口。
- 每次运行记录 `window_start`、`window_end`、`cursor_in`、`cursor_out`。

### 4.7 多阶段漏斗策略

适合 AI World Radar 的核心事件生产。

```text
候选召回：固定源 / 榜单 / search query / watchlist
-> 粗过滤：时间、语言、source、关键词、排除词、最小热度阈值
-> 详情补全：正文、链接、作者、统计、评论、字幕
-> 去重：稳定 ID、canonical URL、content hash、标题时间相似
-> 事件聚合：同一模型/产品/公司/仓库/论文归到同一 EventCluster
-> 证据分级：官方源 > 技术源 > 社区源 > 聚合源
-> 排名：影响力、可信度、新鲜度、热度、中文用户相关性
-> 发布：Evidence Card + Published Event + Brief
```

这个策略比“关键词爬”更可控，因为每一步都有输入、输出和失败原因。

### 4.8 LLM/Agent 语义过滤策略

适合 P1.5/P2，P1 可以少量用于归类。

Agent 不应该直接上网乱搜，而应该在结构化候选上做判断：

- 这条 raw item 是否是 AI 领域事件。
- 它属于发布、融资、开源、论文、政策、事故、价格、争议中的哪一类。
- 是否需要补官方源。
- 是否和已有事件重复。
- 是否只是评论、教程、广告或二次转载。
- 标题中没有关键词但语义上是否重要。

输入应包含：

- source_id、source_level、title、url、published_at。
- excerpt/content。
- platform metrics。
- raw snapshot 指针。
- 已命中的 query_profile 或 watchlist item。

输出应是 JSON，不是自由文本：

```json
{
  "is_ai_event_candidate": true,
  "event_type": "product_release",
  "confidence": 0.78,
  "needs_official_source": true,
  "duplicate_with": null,
  "reason": "Official product launch is discussed by multiple engineering sources."
}
```

### 4.9 变更监控策略

适合 P1/P1.5 的兜底。

做法：

- 对没有 RSS/API 但页面稳定的高价值源建立 watch。
- 保存上次正文快照。
- 新快照与旧快照做 diff。
- 只在页面真的变化时进入 parser / Agent。

参考仓库：

- `dgtlmoon/changedetection.io`：watch、snapshot、diff、last_error、filter failure、LLM intent/summary。
- `huginn/huginn`：Agent schedule、memory checkpoint、expected update period。

AI World Radar 建议：

- P1 可用于少量没有 RSS 的官方页面。
- 不要用它做广域网页爬虫。
- 每个 watch 要配置 include/exclude selector 和 expected_update_period。

## 5. 各平台源码策略拆解

### 5.1 X / Twitter

调研仓库：

- `tweepy/tweepy`
- `DocNow/twarc`
- `vladkens/twscrape`
- `JustAnotherArchivist/snscrape`
- `bocchilorenzo/ntscraper`
- `zedeus/nitter`

#### 官方 API 策略：tweepy / twarc

入口：

- `search_recent_tweets(query, start_time, end_time, since_id, until_id, sort_order)`。
- `search_all_tweets(query, start_time, end_time, next_token)`。
- `get_users_tweets(user_id)`。
- `get_users_mentions(user_id)`。
- tweet lookup、user lookup、counts endpoint。

精准方式：

- 不是爬网页，而是用官方 query 语法精确限定：
  - 实体词：`OpenAI OR Anthropic OR Claude`。
  - 事件词：`launch OR release OR announce OR API OR pricing`。
  - 过滤词：`-is:retweet`、`lang:en`。
  - 时间窗：`start_time/end_time` 或 `since_id/until_id`。
- 对官方账号或 list 做 timeline 采集比全站搜索更稳。
- 用 public metrics 做热度，不把推文本身当事实源。

分页：

- search 走 `next_token`。
- timeline 走 `pagination_token`。
- `tweepy.pagination.Paginator` 会把上一页响应里的 `meta.next_token` 放入下一次请求。

去重：

- tweet ID。
- canonical URL：`https://x.com/{user}/status/{tweet_id}`。
- 对引用/转推要记录 referenced tweet。

适合阶段：

- P1 不建议。
- P1.5/P2 可选，但前提是有官方 API 权限、预算和合规范围。

#### 非官方策略：twscrape / snscrape / Nitter

入口：

- `twscrape`：`SearchTimeline`、`UserTweets`、`TweetDetail`、`ListLatestTweetsTimeline`、trends、community timeline。
- `snscrape`：search、user、hashtag、cashtag、tweet、list、community。
- `ntscraper`：Nitter HTML 实例。

精准方式：

- 支持搜索词、用户、tweet ID、list ID、community ID、trend ID。
- 搜索并不只是关键词，能按用户、列表、趋势等入口精确定位。
- 翻页依赖 GraphQL cursor 或 HTML show-more cursor。

风险：

- guest token、cookie、账号池、proxy、私有 GraphQL、Nitter 实例健康，均不适合 AI World Radar 主链路。
- 这些方案最多借鉴 source health、cursor、失败重试，不应直接上线。

AI World Radar 建议：

- X 在 P1 只保留接口设计，不采。
- 未来优先官方 API。
- 非官方 X scraper 不进入自动发布链路。

### 5.2 Reddit

调研仓库：

- `praw-dev/praw`
- `praw-dev/prawcore`
- `praw-dev/asyncpraw`
- `Pyprohly/redditwarp`
- `JustAnotherArchivist/snscrape`
- `redlib-org/redlib`

#### 官方 API 策略：PRAW / prawcore

入口：

- `reddit.subreddit("LocalLLaMA").hot()`
- `reddit.subreddit("MachineLearning").top(time_filter="day")`
- `reddit.subreddit("OpenAI").search(query, sort="new", time_filter="week")`
- `reddit.submission(id=...)`
- `submission.comments`

精准方式：

- 先限定 subreddit 白名单，再在社区内搜索 AI 事件词。
- 搜索支持 `sort=relevance/hot/top/new/comments`。
- 时间窗支持 `time_filter=hour/day/week/month/year/all`。
- subreddit 的 `hot/top/new` 本身就是平台热度排序。

分页：

- `ListingGenerator` 每次请求 Reddit listing。
- 读取响应里的 `after` cursor。
- 自动把 `after` 放到下一页请求参数。

限流：

- `prawcore.rate_limit.RateLimiter` 读取 `x-ratelimit-remaining`、`x-ratelimit-used`、`x-ratelimit-reset`。
- 根据 reset 和 remaining 计算下一次请求延迟。

热度字段：

- `score`
- `num_comments`
- `upvote_ratio`
- `created_utc`
- `subreddit`
- top comments

去重：

- submission ID。
- comment ID。
- Reddit permalink。
- 外链 canonical URL。

适合 AI World Radar：

- P1.5：作为社区热议候选源。
- 不直接作为事实源。
- 评论只做争议、解释、情绪、热度补充。

#### 非官方/替代前端策略

- `snscrape` Reddit 走 Pushshift 风格接口，支持 user/subreddit/search/submission，使用 `before/after`、`until/since` 时间推进。
- `redlib` 走 Reddit JSON/OAuth，可借鉴 canonical URL、cache、parser。
- 这些不建议作为主路径。

### 5.3 YouTube

调研仓库：

- `googleapis/google-api-python-client`
- `youtube/api-samples`
- `yt-dlp/yt-dlp`
- `LuanRT/YouTube.js`
- `jdepoix/youtube-transcript-api`
- `egbertbouman/youtube-comment-downloader`
- `alexmercerind/youtube-search-python`

#### 官方 API 策略

入口：

- `search.list(q=..., type="video", publishedAfter=..., order=...)`
- `search.list(channelId=..., order="date")`
- `videos.list(id=videoId, part="snippet,statistics,contentDetails")`
- `channels.list(id=channelId)`
- `commentThreads.list(videoId=videoId)`
- `captions.list(videoId=videoId)`

精准方式：

- P1.5 不建议全站关键词扫 YouTube。
- 更稳的做法是：
  - 维护 AI 频道白名单。
  - 每个频道按 `publishedAfter` 拉近期视频。
  - 少量搜索词只做补充发现。
  - 拿到 `videoId` 后再用 `videos.list` 补统计。
  - 只对重要视频拉字幕或少量评论。

分页：

- 官方 client 支持 `pageToken` / `nextPageToken`。

热度字段：

- `viewCount`
- `likeCount`
- `commentCount`
- `publishedAt`
- channel title / channelId

去重：

- `videoId`。
- `channelId + publishedAt + title`。
- 字幕：`videoId + language_code + is_generated`。
- 评论：comment ID。

适合 AI World Radar：

- P1.5：已知频道 + 少量 query + 视频统计。
- Transcript enrichment：只对已入选视频做。
- 评论：默认不采，P2 小样本热议实验。

#### 非官方补全策略

`yt-dlp`：

- 支持 video URL、channel、playlist、tabs。
- 解析 webpage、InnerTube、`ytInitialPlayerResponse`、continuation。
- 能补 `view_count`、`like_count`、`comment_count`、`upload_date`、`subtitles`、`chapters`。
- 太重，不适合作 P1 主采集内核。

`youtube-transcript-api`：

- 入口是已知 `video_id`。
- 按语言优先级查手工字幕、自动字幕、可翻译字幕。
- 异常包括 `IpBlocked`、`RequestBlocked`、`AgeRestricted`、`TranscriptsDisabled`、`NoTranscriptFound`。
- 适合作 enrichment，不适合作发现。

`youtube-comment-downloader`：

- 入口是 `video_id/url`。
- 解析 `ytcfg`、`ytInitialData`，用 InnerTube continuation 抓评论。
- 支持 popular/recent 排序。
- 字段包括 comment id、text、time、author、votes、replies、heart。
- 只建议 P2 小样本使用。

### 5.4 Facebook

调研仓库：

- `mobolic/facebook-sdk`
- `sns-sdks/python-facebook`
- `facebook/facebook-python-business-sdk`
- `kevinzg/facebook-scraper`
- `JustAnotherArchivist/snscrape`

#### 官方 Graph API 策略

入口：

- page ID。
- object ID。
- `get_object(id, fields=...)`。
- `get_connections(id, connection_name, ...)`。
- Page / Post / Comment / Feed edges。

精准方式：

- Graph API 不是匿名关键词爬虫。
- 它适合授权页面、明确 fields、明确 since/until/limit。
- 能否拿 comments、reactions、shares、insights 取决于权限、token、App Review 和 API 版本。

分页：

- `paging.next`。
- cursor `after`。

去重：

- Graph object id。
- post id。
- page id。

适合阶段：

- P2 可选。
- 必须授权、低频、明确数据范围。

#### 非官方 HTML 策略

`facebook-scraper`：

- 支持 page、group、search word、hashtag、post URL。
- 构造 `m.facebook.com` / `mbasic.facebook.com` 页面入口。
- 靠 `next_url`、cursor、page_limit、latest_date 后过滤。
- 解析 HTML/regex 得到 post_id、time、likes、comments、shares、reactions。
- 需要 cookie、登录、2FA、checkpoint 的概率高。

`snscrape` Facebook：

- user/community/group 页面解析。
- Ajax/pagelet 翻页。
- 清洗 permalink、photo、video URL。

AI World Radar 建议：

- Facebook 不进 P1。
- P1.5 也不默认接入。
- P2 只允许 Graph API 授权实验。
- 禁止 cookie 登录、mbasic/mobile HTML 进入生产链路。

### 5.5 GitHub

调研仓库：

- `duanyytop/agents-radar`
- `huchenme/github-trending-api`
- `andygrunwald/go-trending`
- `vitalets/github-trending-repos`

策略一：官方 API 精准采集。

入口：

- org/repo watchlist。
- releases。
- commits。
- issues/PR。
- GitHub Changelog RSS/API。
- Search API。

精准方式：

- 对已知 repo/org 用 GitHub API，比 GitHub Trending 更稳定。
- 可以使用 GitHub 搜索 qualifiers：
  - `topic:ai`
  - `stars:>100`
  - `pushed:>2026-06-01`
  - `language:Python`
  - `org:huggingface`
- 对 repo activity 用 `since` 或 pushed/updated 时间窗。

策略二：Trending 页面解析。

入口：

- `https://github.com/trending`
- language。
- since：daily / weekly / monthly。

精准方式：

- 它不是关键词搜索，而是平台榜单采样。
- 适合发现未知爆发项目。
- 必须保存每日 HTML snapshot。
- selector 失败要报警。

热度字段：

- stars。
- forks。
- stars today。
- language。
- description。
- contributors。

去重：

- repo full_name。
- canonical repo URL。
- snapshot date。

AI World Radar 建议：

- P1：GitHub Changelog、Releases、关键 repo watchlist。
- P1 第二批/P1.5：GitHub Trending 每日一次快照。

### 5.6 Hacker News

调研仓库：

- `HackerNews/API`
- `cheeaun/node-hnapi`
- `duanyytop/agents-radar`

策略一：Firebase 官方 API。

入口：

- `topstories`
- `newstories`
- `beststories`
- `item/{id}`

精准方式：

- 先从 top/new 列表拿 item id。
- 再用 item API 补 title、url、score、descendants、by、time、kids。
- 用规则或 Agent 判断是否 AI 相关。

策略二：Algolia HN Search API。

入口：

- query。
- tags：story/comment。
- numericFilters：created_at_i 时间窗。

精准方式：

- 用 AI query profile 拉近期 stories。
- 与 Firebase item id 去重。
- comments 只作为讨论证据。

热度字段：

- points/score。
- comments count / descendants。
- created_at。

AI World Radar 建议：

- P1 友好源。
- 对“AI 相关事件”优先 Algolia 时间窗搜索。
- 对“工程师圈热点”用 topstories/newstories 后过滤。

### 5.7 Hugging Face

调研仓库：

- `huggingface/huggingface_hub`
- `duanyytop/agents-radar`
- `DIYgod/RSSHub`

入口：

- `list_models`
- `list_datasets`
- `list_spaces`
- Daily Papers。
- repo_id detail。

精准方式：

- 用官方 API 的 `filter`、`author`、`search`、`pipeline_tag`、`sort`、`limit`。
- sort 可选：
  - `downloads`
  - `likes`
  - `last_modified`
  - `trending_score`
  - Daily Papers 的 `publishedAt` / `trending`
- 用 tags/pipeline_tag 限定模型类型。
- 对 repo_id 做详情补全。

热度字段：

- downloads。
- likes。
- trendingScore。
- lastModified。
- tags。
- pipeline_tag。

去重：

- repo_id。
- sha。
- paper id。

AI World Radar 建议：

- P1 可以接 Models/Datasets/Spaces 官方 API。
- Papers/Trending 若 API 不够，再参考 RSSHub/page adapter。

### 5.8 Newsletter / 中文聚合源 / RSSHub

入口：

- RSS feed。
- newsletter archive。
- 邮箱入口。
- RSSHub route。
- 中文 AI 新闻站页面。

精准方式：

- 聚合源只作为候选线索源，不直接当事实源。
- 发现候选后，要反查官方原始链接。
- 对 newsletter 必须保存原文或归档 URL。

RSSHub 策略：

- route registry。
- 每个 route 对应特定站点路径和 parser。
- 输出统一 RSS item。

AI World Radar 建议：

- P1 可以用聚合源作为“漏斗入口”。
- Evidence Card 必须标注 `source_level=aggregator`。
- 发布前优先补官方源。

### 5.9 MediaCrawler

调研仓库：

- `NanmiCoder/MediaCrawler`

支持平台：

- 小红书。
- 抖音。
- 快手。
- B 站。
- 微博。
- 百度贴吧。
- 知乎。

不支持：

- X / Twitter。
- Reddit。
- Facebook。

入口策略：

- `search`：关键词搜索。
- `detail`：指定内容 URL/ID。
- `creator`：作者主页/creator ID。

关键配置：

- `PLATFORM`
- `CRAWLER_TYPE`
- `KEYWORDS`
- `LOGIN_TYPE`
- `COOKIES`
- `ENABLE_IP_PROXY`
- `SAVE_LOGIN_STATE`
- `CRAWLER_MAX_NOTES_COUNT`
- `ENABLE_GET_COMMENTS`
- `ENABLE_GET_SUB_COMMENTS`

精准方式：

- 不是只有关键词。
- 搜索模式用于召回。
- detail 模式用于精确补内容。
- creator 模式用于追踪作者主页。
- 平台 client 负责私有 endpoint、签名、cookie 更新、评论游标。
- store 层按内容 ID 更新或落库。

风险：

- 登录态。
- cookie。
- 二维码/手机号登录。
- 代理池。
- stealth 脚本。
- 平台风控。
- 非商业学习许可证。

AI World Radar 建议：

- 不作为 P1/P1.5 依赖。
- P2 只可借鉴架构：
  - adapter factory。
  - `search/detail/creator` 三入口。
  - crawler/login/client/store 分层。
  - 采集上限。
  - 登录/代理/评论深度风险字段显式化。

## 6. AI World Radar 推荐采集策略组合

### 6.1 P1 稳定源组合

目标：先做可回源、低风险、能发布的 AI 事件。

策略：

- 官方 RSS/API。
- 固定官方博客页面。
- GitHub Changelog/Releases。
- Hacker News API/Algolia。
- Hugging Face 官方 API。
- 少量中文聚合源作为线索。

不做：

- X 非官方。
- Facebook HTML。
- YouTube 评论广域采集。
- MediaCrawler 登录态采集。
- Browser 自动化主链路。

### 6.2 P1.5 热度增强组合

目标：在稳定事实源之外增加热度信号和早期发现。

策略：

- Reddit 官方 API：subreddit whitelist + query + sort + time_filter。
- YouTube Data API：channel whitelist + publishedAfter + videos.list statistics。
- GitHub Trending：每日快照。
- Hugging Face Trending/Daily Papers。
- changedetection：少量无 RSS 的高价值页面。
- Agent 语义过滤：候选级，不直接上网。

### 6.3 P2 高风险/实验组合

目标：只在有明确价值、授权和风险预算时实验。

策略：

- X 官方 API。
- Facebook Graph API 授权页面。
- YouTube transcript/comment enrichment。
- 中文社媒小规模授权实验。
- Browser worker 和 LLM extraction fallback。

禁止默认使用：

- cookie 登录绕限制。
- 账号池。
- 代理池绕风控。
- 私有 GraphQL 作为生产事实源。
- 抓取私密内容。

## 7. 推荐 Query Profile 设计

关键词不应写死在代码里，应配置成 query profile。

```yaml
id: ai_product_release_global
stage: P1.5
purpose: 发现 AI 产品/模型/开发工具发布事件
languages:
  - en
  - zh
entities:
  companies:
    - OpenAI
    - Anthropic
    - Google DeepMind
    - NVIDIA
    - Meta AI
    - Microsoft AI
  products:
    - ChatGPT
    - Claude
    - Gemini
    - Cursor
    - Copilot
    - MCP
    - Sora
    - vLLM
    - Ollama
event_terms:
  release:
    - launch
    - release
    - announce
    - rollout
    - preview
  engineering:
    - API
    - SDK
    - agent
    - coding agent
    - benchmark
    - open source
  business:
    - pricing
    - funding
    - acquisition
negative_terms:
  - coupon
  - giveaway
  - job
  - hiring
  - meme
platform_overrides:
  reddit:
    subreddits:
      - LocalLLaMA
      - MachineLearning
      - OpenAI
    sort:
      - top
      - new
    time_filter: day
  hacker_news:
    tags:
      - story
    window_hours: 48
  youtube:
    channel_whitelist: true
    published_after_hours: 72
  x:
    official_api_only: true
    exclude_retweets: true
dedupe_keys:
  - canonical_url
  - platform_item_id
  - normalized_title_date
```

## 8. 推荐 Adapter Manifest 字段

```yaml
source_id: reddit_localllama_ai_search
display_name: Reddit LocalLLaMA AI Search
platform: reddit
source_kind: community
priority_stage: P1.5
collector_mode: api_search
entrypoints:
  - subreddit: LocalLLaMA
query_profile_id: ai_product_release_global
auth_profile: reddit_readonly_oauth
schedule:
  interval_minutes: 180
fetch_policy:
  max_pages: 3
  timeout_seconds: 20
  sort: top
  time_filter: day
watermark_policy:
  type: cursor_and_time
  cursor_field: after
  time_field: created_utc
normalize_policy:
  item_id: reddit_submission_id
  canonical_url: permalink
  external_url: url
dedupe_keys:
  - platform_item_id
  - external_url
  - normalized_title_date
metrics:
  - score
  - num_comments
  - upvote_ratio
risk_flags:
  login_required: false
  cookie_required: false
  unofficial_api: false
  comments_enabled: shallow
source_level: community_signal
quality_gate:
  require_official_confirmation_for_publish: true
```

## 9. 推荐事件发现流水线

```text
1. Source Registry 读取启用源
2. Scheduler 按 source interval 创建 pipeline_run
3. Adapter fetch list/search/trending
4. 保存 raw snapshot
5. Normalizer 生成 Raw Item
6. Rule Filter 做时间、语言、关键词、排除词、source_level 过滤
7. Enrichment Worker 对高价值候选补 detail/comment/transcript/repo stats
8. Dedupe Worker 按 ID、URL、hash、标题时间合并
9. Agent Candidate Judge 判断是否 AI 事件候选
10. Event Clusterer 聚合同一事件
11. Evidence Card Builder 标注来源等级和证据摘要
12. Ranker 计算重要性
13. Quality Gate 检查可回源、结构、谨慎表达
14. Published Event / Brief 入库
```

## 10. “精准爬取”开发优先级

### 第一优先级：P1 可立即实现

- RSS collector：OpenAI / Anthropic / DeepMind / NVIDIA。
- GitHub Changelog / Releases collector。
- HN Algolia collector：query + numeric time window。
- Hugging Face model collector：sort by `trending_score` / `last_modified`。
- Raw snapshot + dedupe。
- Query profile 配置文件。

### 第二优先级：P1.5 增强

- Reddit PRAW collector。
- YouTube Data API collector。
- GitHub Trending snapshot collector。
- changedetection-style page watch collector。
- Agent candidate judge。
- EventCluster 跨源聚合。

### 第三优先级：P2 实验

- X 官方 API collector。
- Facebook Graph API collector。
- YouTube transcript enrichment。
- YouTube comment sampler。
- Browser fallback worker。
- 中文社媒授权实验。

## 11. 反模式清单

不要这样做：

- 让 Agent 拿几个关键词直接全网搜索并决定发布。
- 把 X / Facebook 非官方 scraper 当 P1 数据源。
- 用 cookie、账号池、代理池绕过登录或风控。
- 把 Reddit/HN/YouTube 评论当事实证据。
- 只存摘要，不存 raw snapshot。
- 只按标题去重，不用平台稳定 ID。
- GitHub Trending 高频抓取。
- YouTube 评论广域抓取。
- 中文社媒登录态采集进入自动发布链路。
- 热度高就直接发布，不补官方源。

## 12. 给后续开发 Agent 的执行建议

如果后续开发 Agent 要开始写采集系统，建议从这个顺序开始：

1. 先实现 `source_registry.yaml` 和 `query_profiles.yaml`。
2. 先写 RSS/API adapter，不写浏览器爬虫。
3. 每个 adapter 必须输出统一 Raw Item。
4. 每次 fetch 必须保存 raw snapshot。
5. 每个 source 必须有水位字段和 source health。
6. 每个平台先只做一个最小闭环：
   - RSS：OpenAI News。
   - HN：Algolia query + 48 小时时间窗。
   - GitHub：Changelog 或一个 repo release。
   - HF：list_models sort by trending_score。
7. 跑通后再接 Reddit/YouTube。
8. X/Facebook/MediaCrawler 类方案只保留设计扩展点，不进入 P1。

## 13. GitHub 仓库学习链接

这一节专门给后续学习源码使用。建议学习顺序是：先看 P1 稳定源，再看 P1.5 热度源，最后看高风险社媒项目。

### 13.1 P1 稳定源优先学习

| 仓库 | GitHub 链接 | 建议重点看 | 能学到什么 |
|---|---|---|---|
| feedparser | https://github.com/kurtmckee/feedparser | `feedparser/api.py`, `feedparser/http.py` | RSS/Atom 解析、bozo 异常、feed entries 结构 |
| RSSHub | https://github.com/DIYgod/RSSHub | `lib/registry.ts`, `lib/routes/*` | route registry、站点 adapter、统一 RSS 输出 |
| Miniflux | https://github.com/miniflux/v2 | `internal/reader/*`, `internal/storage/entry.go` | feed fetch、ETag、Last-Modified、entry hash、worker |
| Huginn | https://github.com/huginn/huginn | `app/models/agents/rss_agent.rb`, `website_agent.rb` | agent schedule、memory checkpoint、source health |
| changedetection.io | https://github.com/dgtlmoon/changedetection.io | `changedetectionio/worker.py`, processors | 页面快照、diff、selector/filter、错误状态 |
| HackerNews/API | https://github.com/HackerNews/API | README API docs | HN top/new/item 官方 API |
| node-hnapi | https://github.com/cheeaun/node-hnapi | `lib/hnapi.js`, `lib/cache.js` | HN API cache、item 封装、评论结构 |
| huggingface_hub | https://github.com/huggingface/huggingface_hub | `src/huggingface_hub/hf_api.py` | HF models/datasets/spaces/papers API、sort/filter |
| agents-radar | https://github.com/duanyytop/agents-radar | `src/github.ts`, `src/hf.ts`, `src/hn.ts` | AI digest 的 GitHub/HF/HN 时间窗采集 |

### 13.2 P1.5 热度源优先学习

| 仓库 | GitHub 链接 | 建议重点看 | 能学到什么 |
|---|---|---|---|
| PRAW | https://github.com/praw-dev/praw | `praw/models/reddit/subreddit.py`, `listing/generator.py` | subreddit/search/top/hot、after cursor |
| prawcore | https://github.com/praw-dev/prawcore | `prawcore/rate_limit.py`, `sessions.py` | Reddit rate limit headers、429、retry |
| asyncpraw | https://github.com/praw-dev/asyncpraw | async modules | Reddit 异步 API wrapper |
| redditwarp | https://github.com/Pyprohly/redditwarp | `redditwarp/core/rate_limited_SYNC.py` | token bucket rate budget |
| youtube/api-samples | https://github.com/youtube/api-samples | `python/search.py`, `comment_threads.py`, `captions.py` | YouTube Data API 的 search/video/comment/caption |
| google-api-python-client | https://github.com/googleapis/google-api-python-client | `googleapiclient/discovery.py`, `http.py` | pageToken/nextPageToken、Google API client |
| yt-dlp | https://github.com/yt-dlp/yt-dlp | `yt_dlp/extractor/youtube/_video.py`, `_tab.py`, `_search.py` | YouTube 元数据、频道/playlist、continuation |
| YouTube.js | https://github.com/LuanRT/YouTube.js | `src/Innertube.ts`, `src/core/Session.ts` | InnerTube client、search/info/comments |
| youtube-transcript-api | https://github.com/jdepoix/youtube-transcript-api | `youtube_transcript_api/_api.py`, `_transcripts.py` | videoId 字幕 enrichment |
| youtube-comment-downloader | https://github.com/egbertbouman/youtube-comment-downloader | `youtube_comment_downloader/downloader.py` | 评论 continuation、popular/recent comments |
| github-trending-api | https://github.com/huchenme/github-trending-api | `src/functions/utils/fetch.js` | GitHub Trending Cheerio selector |
| go-trending | https://github.com/andygrunwald/go-trending | `trending.go` | GitHub Trending goquery parser |
| github-trending-repos | https://github.com/vitalets/github-trending-repos | `scripts/helpers/trends.js` | GitHub Trending 每日快照 |

### 13.3 P2 / 高风险策略只读学习

| 仓库 | GitHub 链接 | 建议重点看 | 能学到什么 | 风险 |
|---|---|---|---|---|
| tweepy | https://github.com/tweepy/tweepy | `tweepy/client.py`, `tweepy/pagination.py` | X 官方 API search/timeline/pagination | API 权限/预算 |
| twarc | https://github.com/DocNow/twarc | `src/twarc/client2.py`, decorators | X 官方 API 归档、hydration、dedupe | API 权限/预算 |
| twscrape | https://github.com/vladkens/twscrape | `twscrape/api.py`, `accounts_pool.py` | X GraphQL、cursor、账号池限流 | 非官方、账号/cookie/proxy |
| snscrape | https://github.com/JustAnotherArchivist/snscrape | `snscrape/modules/twitter.py`, `reddit.py`, `facebook.py` | 多平台非官方 scraper、guest token、cursor | 稳定性/合规风险 |
| ntscraper | https://github.com/bocchilorenzo/ntscraper | `ntscraper/nitter.py` | Nitter 实例健康、HTML cursor | 公开实例不稳定 |
| nitter | https://github.com/zedeus/nitter | service code | X 替代前端原理 | 不适合作依赖 |
| redlib | https://github.com/redlib-org/redlib | `src/client.rs`, `oauth.rs`, `post.rs` | Reddit canonical URL/cache/parser | 替代前端风险 |
| facebook-sdk | https://github.com/mobolic/facebook-sdk | `facebook/__init__.py` | Facebook Graph API object/connection | 授权和权限限制 |
| python-facebook | https://github.com/sns-sdks/python-facebook | `pyfacebook/api/graph.py` | Graph API wrapper、cursor | 授权和权限限制 |
| facebook-python-business-sdk | https://github.com/facebook/facebook-python-business-sdk | Business SDK modules | Marketing/Business API | 不是公开新闻采集 |
| facebook-scraper | https://github.com/kevinzg/facebook-scraper | `facebook_scraper.py`, `extractors.py` | mobile/mbasic HTML、comments/reactions | cookie/login/checkpoint |
| MediaCrawler | https://github.com/NanmiCoder/MediaCrawler | `main.py`, `config/base_config.py`, `media_platform/*` | 多平台 adapter、search/detail/creator、登录态/代理风险字段 | 非商业许可证、登录/风控 |
| Crawlee | https://github.com/apify/crawlee | `packages/basic-crawler/*` | requestQueue、retry、sessionPool、browser worker | P1 太重 |
| Firecrawl | https://github.com/firecrawl/firecrawl | API controller/types | AI-friendly crawl API、markdown/rawHtml/screenshot | 不应绑定核心 |
| Crawl4AI | https://github.com/unclecode/crawl4ai | `crawl4ai/async_webcrawler.py` | LLM-friendly extraction、cache mode | 不能替代原始证据 |
| ScrapeGraphAI | https://github.com/ScrapeGraphAI/Scrapegraph-ai | `scrapegraphai/graphs/*`, `nodes/*` | LLM extraction graph | P1 不做主链路 |
| Scrapy | https://github.com/scrapy/scrapy | downloader middlewares, retry | 通用爬虫框架、retry、pipeline | P1 可能过重 |

## 14. 仓库策略速查表

| 仓库 | 精准入口 | 候选召回 | 分页/水位 | 热度字段 | 推荐 |
|---|---|---|---|---|---|
| [feedparser](https://github.com/kurtmckee/feedparser) | feed URL | RSS item | etag / modified / published | 无 | P1 |
| [RSSHub](https://github.com/DIYgod/RSSHub) | route namespace | 站点 route | route cache | route 自定义 | P1 参考 |
| [Miniflux](https://github.com/miniflux/v2) | feed URL | entry | ETag / Last-Modified / hash | 无 | P1 参考 |
| [Huginn](https://github.com/huginn/huginn) | agent config | RSS/API/page | schedule / memory | 自定义 | P1 参考 |
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io) | watch URL | 页面变化 | snapshot / diff | change detected | P1/P1.5 |
| [tweepy](https://github.com/tweepy/tweepy) | query/user/tweet | 官方 API | next_token / since_id / time | public metrics | P1.5/P2 |
| [twarc](https://github.com/DocNow/twarc) | query/user/tweet | 官方 API 归档 | pagination / hydration | public metrics | P1.5/P2 |
| [twscrape](https://github.com/vladkens/twscrape) | search/user/tweet/list/trend | 私有 GraphQL | cursor / account lock | view/like/repost | 不建议 |
| [snscrape](https://github.com/JustAnotherArchivist/snscrape) | search/user/hashtag | guest token/HTML/API | cursor / retry | 平台字段 | 不建议 |
| [PRAW](https://github.com/praw-dev/praw) | subreddit/search/submission | 官方 Reddit API | after cursor | score/comments/upvote | P1.5 |
| [prawcore](https://github.com/praw-dev/prawcore) | Reddit HTTP | API response | x-ratelimit headers | 无 | P1.5 参考 |
| [youtube/api-samples](https://github.com/youtube/api-samples) | q/channel/videoId | YouTube Data API | pageToken | views/likes/comments | P1.5 |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | video/channel/playlist | webpage/InnerTube | continuation | views/likes/comments | P1.5/P2 fallback |
| [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) | videoId | 字幕列表 | 无 | 字幕可用性 | P1.5 enrichment |
| [youtube-comment-downloader](https://github.com/egbertbouman/youtube-comment-downloader) | videoId | 评论 continuation | continuation | votes/replies | P2 |
| [facebook-sdk](https://github.com/mobolic/facebook-sdk) | object/page edge | Graph API | paging.next | reactions/comments | P2 授权 |
| [facebook-scraper](https://github.com/kevinzg/facebook-scraper) | page/group/search/hashtag | mobile HTML | next_url | likes/comments/shares | 不建议 |
| [github-trending-api](https://github.com/huchenme/github-trending-api) | trending URL | HTML 榜单 | since daily/weekly | stars today | P1 第二批 |
| [go-trending](https://github.com/andygrunwald/go-trending) | trending URL | HTML 榜单 | since/language | stars/forks | P1 第二批 |
| [node-hnapi](https://github.com/cheeaun/node-hnapi) | HN list/item | Firebase API | item id list | score/comments | P1 |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | list_models/datasets/spaces | 官方 API | limit/sort/filter | downloads/likes/trending | P1 |
| [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | search/detail/creator | 中文社媒 | page/cursor/content id | likes/comments/shares | P2 研究参考 |

## 15. 参考链接

- https://github.com/kurtmckee/feedparser
- https://github.com/DIYgod/RSSHub
- https://github.com/miniflux/v2
- https://github.com/huginn/huginn
- https://github.com/dgtlmoon/changedetection.io
- https://github.com/tweepy/tweepy
- https://github.com/DocNow/twarc
- https://github.com/vladkens/twscrape
- https://github.com/JustAnotherArchivist/snscrape
- https://github.com/praw-dev/praw
- https://github.com/praw-dev/prawcore
- https://github.com/youtube/api-samples
- https://github.com/googleapis/google-api-python-client
- https://github.com/yt-dlp/yt-dlp
- https://github.com/LuanRT/YouTube.js
- https://github.com/jdepoix/youtube-transcript-api
- https://github.com/egbertbouman/youtube-comment-downloader
- https://github.com/mobolic/facebook-sdk
- https://github.com/sns-sdks/python-facebook
- https://github.com/kevinzg/facebook-scraper
- https://github.com/huggingface/huggingface_hub
- https://github.com/HackerNews/API
- https://github.com/cheeaun/node-hnapi
- https://github.com/NanmiCoder/MediaCrawler
