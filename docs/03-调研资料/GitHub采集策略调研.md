# GitHub 采集策略调研

更新时间：2026-06-03

## 1. 调研目的

本次调研的目的不是立刻为 AI World Radar 引入某一个采集库，也不是实际爬取 X、Reddit、YouTube 或 Facebook，而是通过 GitHub 开源项目的源码实现，反推出后续采集系统应该采用哪些稳定策略、应该避免哪些高风险策略。

调研重点分为两类：

- 高热平台采集：X / Twitter、Reddit、YouTube、Facebook。
- P1 当前信息源采集：OpenAI News、Anthropic News、Google DeepMind Blog、NVIDIA RSS / Blog、GitHub Changelog、GitHub Trending、Hacker News API、Hugging Face Papers / Models / Trending、TLDR AI、AIBase，以及其他 AI 新闻/RSS/Newsletter 聚合源。

本报告优先回答三个问题：

1. 哪些采集方式适合 AI World Radar 的 P1 冷启动。
2. 哪些方式适合 P1.5 作为热度增强。
3. 哪些方式因为登录、cookie、反爬、账号、ToS 或稳定性风险，不应进入 P1。

## 2. 与 AI World Radar 的关系

AI World Radar 的核心不是新闻链接列表，而是“可回源、可聚合、可解释”的 AI 圈事件雷达。采集系统要服务于项目既定的内部链路：

```text
Source Registry
  -> Raw Snapshot
  -> Raw Item
  -> Evidence Card
  -> Event Cluster
  -> Published Event
```

因此，采集层不能只追求“抓到内容”，还必须保留以下能力：

- 可追溯：每一条 Evidence Card 都能回到原始 URL、原始响应或快照。
- 可复跑：适配器版本、抓取时间、HTTP headers、ETag、Last-Modified、状态码要能记录。
- 可降级：RSS/API 失败时进入重试和 source health，而不是直接让 Agent 猜。
- 可分级：P1 先用稳定公开源；X、Reddit、YouTube 等热度源进入 P1.5；Facebook 与 X 的非官方方案默认高风险。
- 可解释：采集系统输出 Raw Item，Agent 再做语义判断，不让 LLM 直接替代事实证据。

## 3. 总体结论

### 3.1 P1 结论

P1 应采用“轻量自建 Source Registry + Adapter Manifest + Raw Snapshot Store + Normalizer”的架构，采集方式优先级如下：

1. 官方 RSS / Atom / JSON Feed。
2. 官方 API 或公开稳定 API。
3. 稳定公开 HTML 页面解析。
4. RSSHub 等成熟路由项目作为源码参考或备选路由，而不是整体依赖。

P1 最适合先落地：

- `feedparser` 风格的 RSS/Atom/JSON Feed 解析。
- Hugging Face 官方 API。
- Hacker News 官方 Firebase API 或 Algolia HN Search API。
- GitHub 官方 API / Releases / Changelog RSS。
- OpenAI、Anthropic、DeepMind、NVIDIA、AIBase 等官方博客/RSS/稳定页面 adapter。
- Raw Snapshot、Raw Item、Evidence Card 的数据边界。

### 3.2 P1.5 结论

P1.5 再引入高热度增强源：

- Reddit：优先官方 API/PRAW；可采集指定 subreddit、搜索、评论数、upvote、发布时间。
- YouTube：优先 YouTube Data API；字幕和评论只作为已知视频的补充证据，不做 P1 广域抓取。
- GitHub Trending / Hugging Face Papers：HTML 页面或非核心 API 可做每日快照，必须配 selector test 和失败降级。
- Browser worker / LLM fallback：仅用于高价值源失败兜底，不能作为事实证据唯一来源。

### 3.3 P2 或不建议结论

X / Twitter 与 Facebook 的非官方采集方案不应进入 P1：

- X 非官方方案大量依赖 guest token、GraphQL 私有接口、cookie、账号池、代理或登录态，稳定性和合规风险高。
- Facebook HTML 方案大量依赖 mobile/mbasic 页面、cookie、登录、checkpoint/2FA，账号风险明显。
- Nitter 一类代理前端不应作为生产数据源依赖。

X / Facebook 若未来确需接入，应优先考虑官方 API、合规授权、明确的数据范围和独立风险预算。

## 4. 高热平台采集策略

### 4.1 X / Twitter

调研仓库：

- `vladkens/twscrape`
- `JustAnotherArchivist/snscrape`
- `tweepy/tweepy`
- `DocNow/twarc`
- `bocchilorenzo/ntscraper`
- `zedeus/nitter`

源码策略：

- `tweepy/tweepy` 是官方 X API/Twitter API wrapper。关键源码在 `tweepy/client.py`、`tweepy/pagination.py`、`tweepy/auth.py`、`tweepy/errors.py`。它使用 bearer token/OAuth，`Client` 支持 `wait_on_rate_limit`，分页器围绕 `pagination_token`、`next_token` 迭代。优点是合规路径更清楚；缺点是需要 API 权限、费用、额度与平台政策稳定性。
- `vladkens/twscrape` 是非官方 X scraper。关键源码在 `twscrape/accounts_pool.py`、`twscrape/account.py`、`twscrape/login.py`、`twscrape/api.py`、`twscrape/queue_client.py`。它使用 SQLite 管账号池、cookie、proxy、active 状态、queue locks、stats，`lock_until()`、`get_for_queue_or_wait()` 等实现队列级账号限流。
- `JustAnotherArchivist/snscrape` 在 `snscrape/modules/twitter.py` 中维护 guest token，遇到 403/404/429 会 unset/block token，再重新获取；`snscrape/base.py` 有指数退避 retry。它还使用 Twitter GraphQL/private endpoint 与 cursor。
- `zedeus/nitter` 是替代前端/代理类项目，本身可作为观察 X 生态的样本，但不适合作为 AI World Radar 的生产依赖。
- `DocNow/twarc` 是偏归档/研究场景的官方 API 工具，源码中有 rate limit decorator、`_paginate`、hydration、compliance jobs、deduplicate 等设计，适合借鉴“归档式采集 + 合规删除/补全”的思路。
- `bocchilorenzo/ntscraper` 依赖 Nitter 实例健康检查、随机实例、HTML 解析和 show-more/cursor 翻页，可借鉴实例健康检查，但不适合生产依赖公开 Nitter 实例。

适合借鉴：

- `twscrape` 的 per-source lock、`next_available_at`、source/account health、stats 思路，可以迁移成 AI World Radar 的 source health，而不是账号池。
- `snscrape/base.py` 的 retry/backoff 与错误日志可借鉴。
- `tweepy` 的 token/API/pagination 抽象可作为未来官方 API adapter 参考。

不适合 P1：

- 账号池、cookie 登录、guest token、私有 GraphQL、代理轮换均不适合 P1。
- 不建议绕过登录、不建议抓取私密内容、不建议将 X 非官方接口作为核心事实源。

推荐阶段：

- 官方 API：P1.5 / P2，前提是有明确预算、授权和范围。
- 非官方 scraper：不建议进入产品主链路；最多作为离线研究，不进入自动发布链路。

### 4.2 Reddit

调研仓库：

- `praw-dev/praw`
- `praw-dev/prawcore`
- `praw-dev/asyncpraw`
- `Pyprohly/redditwarp`
- `redlib-org/redlib`
- `JustAnotherArchivist/snscrape`

源码策略：

- `praw-dev/praw` 是 Reddit 官方 API wrapper。关键源码在 `praw/reddit.py`、`praw/models/listing/generator.py`。
- `praw-dev/prawcore` 在 `prawcore/sessions.py`、`prawcore/rate_limit.py`、`prawcore/exceptions.py` 中封装 retry、429、`x-ratelimit-reset`、`x-ratelimit-remaining`、`x-ratelimit-used`。
- `ListingGenerator` 使用 `after` cursor 做分页。
- `snscrape/modules/reddit.py` 使用 Pushshift/old Reddit 风格接口，源码里有 429 sleep、Pushshift `until` 参数迭代、submission/comment 区分。
- `redditwarp` 的 `rate_limited_SYNC.py` / `rate_limited_ASYNC.py` 使用 token bucket，并根据 Reddit `x-ratelimit-remaining/reset/used` 动态调整，可作为通用 rate budget 参考。
- `redlib` 是 Reddit 替代前端，使用 `oauth.reddit.com` / `www.reddit.com` `.json` 与 token daemon，适合观察 canonical URL、post/comment parser 和 cache，但 mobile spoof 风险不适合生产。

适合 AI World Radar 的热度信号：

- subreddit：`r/MachineLearning`、`r/LocalLLaMA`、`r/OpenAI`、`r/singularity` 等。
- 字段：标题、URL、作者、发布时间、score、comments_count、upvote ratio、subreddit、top comments。
- 用途：P1.5 的“热议型候选事件”信号，不直接作为事实发布源。

风险与边界：

- 使用官方 API 比 HTML/Pushshift 稳定。
- Reddit 内容需要区分事实来源和社区讨论，评论不能直接当作事实。
- P1 不必接入 Reddit；P1.5 可用官方 API 做有限范围采集。

推荐阶段：

- P1.5：官方 API/PRAW，指定 subreddit + query。
- 不建议：把 Pushshift 或旧页面 scraper 作为主路径。

### 4.3 YouTube

调研仓库：

- `googleapis/google-api-python-client`
- `yt-dlp/yt-dlp`
- `jdepoix/youtube-transcript-api`
- `egbertbouman/youtube-comment-downloader`
- `pytube/pytube`
- `youtube/api-samples`
- `LuanRT/YouTube.js`
- `alexmercerind/youtube-search-python`

源码策略：

- `googleapis/google-api-python-client` 是官方 Google API client。关键源码在 `googleapiclient/discovery.py`、`googleapiclient/http.py`。YouTube Data API 可获取视频、频道、搜索、播放量、点赞数、发布时间等，优点是合规稳定，缺点是需要 API key/配额。
- `yt-dlp/yt-dlp` 的 YouTube 提取逻辑已经拆到 `yt_dlp/extractor/youtube/_video.py`、`_tab.py`、`_base.py` 等文件；源码和测试覆盖 `view_count`、`like_count`、`comment_count`、`upload_date`、`subtitles`、`chapters` 等字段。它很强，但目标是下载/提取，不适合 P1 作为采集主内核。
- `youtube-transcript-api` 关键源码在 `youtube_transcript_api/_api.py`、`_transcripts.py`、`proxies.py`。它不要求 API key，可取字幕/自动字幕；源码对 429 映射为 `IpBlocked`，有 `TranscriptsDisabled`、`NoTranscriptFound`、`AgeRestricted`、`RequestBlocked` 等异常。
- `youtube-comment-downloader` 在 `youtube_comment_downloader/downloader.py` 中解析 `ytcfg`、`ytInitialData`、continuation token 和 Innertube 请求，可拿评论、点赞、回复等，但属于非官方页面/内部接口路径。
- `youtube/api-samples` 是官方 YouTube Data API 样例仓库，覆盖 `search.list`、`videos.list`、`channels.list`、`commentThreads.list`、`captions.list/download` 等路径；样例较老，但配合 `google-api-python-client` discovery 仍能说明官方 API 采集模型。
- `LuanRT/YouTube.js` / `youtubei.js` 是 TypeScript InnerTube 客户端，源码中有 `Innertube.create()`、channel、search、continuation、comments parser 和 OAuth/cookie header 支持，适合 P1.5 实验。
- `youtube-search-python` 已长期未维护，但它的 search/video/channel/comments/transcript 模块可作为字段结构参考，不建议引入。

适合 AI World Radar 的热度信号：

- 视频标题、频道、发布时间、播放量、点赞数、评论数。
- 已知视频的 transcript 可辅助 Evidence Card 和摘要。
- 评论只适合做热议补充，不适合事实证据主来源。

推荐阶段：

- P1.5：YouTube Data API，用于少量 AI 频道、关键词或已知视频热度。
- P1.5 / P2：transcript enrichment，仅对已知重要视频使用。
- 不建议 P1：评论广域抓取、Innertube 私有接口、绕过限制或依赖代理。

### 4.4 Facebook

调研仓库：

- `mobolic/facebook-sdk`
- `sns-sdks/python-facebook`
- `facebook/facebook-python-business-sdk`
- `kevinzg/facebook-scraper`
- `JustAnotherArchivist/snscrape`

源码策略：

- `mobolic/facebook-sdk` 是 Graph API SDK。关键源码在 `facebook/__init__.py`，`GraphAPI` 使用 `access_token`、API version、`get_object()`、`get_connections()`、paging `next` 来访问 Graph API。优点是合规路径明确；缺点是权限和可访问数据有限。
- `kevinzg/facebook-scraper` 使用 mobile/mbasic 页面解析。关键源码在 `facebook_scraper/facebook_scraper.py`、`page_iterators.py`、`extractors.py`。它支持 `get_posts`、hashtag、search、group、comments、reactions、shares、cookies、credentials、proxies；遇到 login/checkpoint 会抛出或要求登录/2FA/approval。
- `snscrape/modules/facebook.py` 也包含 Facebook user/community/group 页面解析，稳定性同样受页面变化影响。
- `sns-sdks/python-facebook` / `pyfacebook` 是较新的 Graph API wrapper，源码中有 Page/Post/Comment/Feed edges、cursor paging、rate-limit header 和 sleep 处理，适合授权场景参考。
- `facebook-python-business-sdk` 是 Meta 官方 Business/Marketing API SDK，主要面向广告、商业资产和 insights，不是公开页面/帖子采集库。

风险判断：

- Facebook 非官方 HTML 采集涉及登录、cookie、checkpoint、账号限制，且页面结构极易变化。
- AI World Radar P1 不需要 Facebook。
- 即使 P1.5 也不建议默认接入 Facebook，除非只采集官方授权页面或使用 Graph API。

推荐阶段：

- 官方 Graph API：P2 可选，前提是有明确授权和数据范围。
- HTML scraper：不建议进入自动化产品链路。

## 5. P1 稳定信息源采集策略

### 5.1 官方博客 / RSS

相关仓库：

- `kurtmckee/feedparser`
- `DIYgod/RSSHub`
- `miniflux/v2`
- `huginn/huginn`

策略结论：

- OpenAI News、Anthropic News、Google DeepMind Blog、NVIDIA Blog/RSS 这类源，P1 应优先走 RSS/Atom/JSON Feed 或稳定公开页面。
- `feedparser/api.py` 的 `parse()` 支持 URL、文件、bytes、string，并支持 `etag`、`modified` 条件请求参数，适合作为 P1 RSS collector 的解析层。
- `RSSHub` 的 `lib/registry.ts` 把 `lib/routes` 下的 route/namespace 动态注册成路由，适合借鉴 source adapter 组织方式。子代理 C 还确认 RSSHub 已有 OpenAI、Anthropic、DeepMind、GitHub Trending、Hugging Face Daily Papers、AIBase 等相关路由路径。
- `miniflux/v2` 的 fetcher/parser/storage/worker 分层适合借鉴 ETag、Last-Modified、entry hash、worker pool 和 feed error。
- `huginn/huginn` 的 `WebsiteAgent`/`RSSAgent`/`Agent` 模型适合借鉴 expected update period、memory checkpoint 和 health 判断。

P1 建议：

- 第一批 source 只维护“官方 URL + parser + normalize + dedupe”。
- 不要让 LLM 直接读网页决定事实，LLM 只处理 Evidence Card 后的语义层。
- 每个 adapter 必须保存 raw snapshot 指针和 parser version。

### 5.2 GitHub

相关仓库：

- `duanyytop/agents-radar`
- `huchenme/github-trending-api`
- `andygrunwald/go-trending`
- `vitalets/github-trending-repos`

策略结论：

- GitHub Changelog / Releases / Issues / PRs 适合官方 GitHub API。
- `agents-radar/src/github.ts` 使用 GitHub API、`GITHUB_TOKEN`、`per_page`、分页和 `since` 截止时间，适合 P1 借鉴。
- GitHub Trending 没有正式官方 API，`github-trending-api` 和 `go-trending` 都是解析 `https://github.com/trending` HTML。`github-trending-api/src/functions/utils/fetch.js` 使用 `cheerio` 解析 trending 页面；`go-trending/trending.go` 使用 goquery。
- Trending HTML 解析可以做，但必须保存每日快照、selector test、失败报警和 fallback。

P1 建议：

- GitHub Changelog、release、repo activity 走官方 API/RSS。
- GitHub Trending 作为 P1 第二批或 P1.5 热度源，默认每日采样，不要高频抓取。

### 5.3 Hacker News

相关仓库：

- `HackerNews/API`
- `cheeaun/node-hnapi`
- `duanyytop/agents-radar`

策略结论：

- HN 官方 Firebase API 是 P1 友好源，公开、稳定、无需登录。
- `node-hnapi/lib/hnapi.js` 使用 Firebase `https://hacker-news.firebaseio.com`，封装 `news`、`newest`、`ask`、`show`、`jobs`、`item`、comments；`lib/cache.js` 提供 memory/Redis cache。
- `agents-radar/src/hn.ts` 走 Algolia HN Search API，按关键词和时间窗口拉取 AI 相关 stories。

P1 建议：

- 如果目标是“AI 相关事件”，优先 Algolia HN Search API 按关键词/时间窗口采样。
- 如果目标是“全站热点”，使用官方 Firebase topstories/newstories 后再由规则/Agent 过滤。
- HN comments 可以作为热议证据，但不能直接作为事实主来源。

### 5.4 Hugging Face

相关仓库：

- `huggingface/huggingface_hub`
- `duanyytop/agents-radar`
- `DIYgod/RSSHub`

策略结论：

- `huggingface_hub/src/huggingface_hub/hf_api.py` 提供 `list_models`、`list_datasets`、`list_spaces` 等官方 API；sort 类型包括 `downloads`、`likes`、`last_modified`、`trending_score`；Daily Papers sort 包含 `publishedAt`、`trending`。
- 模型/数据集/Space 的 `downloads`、`likes`、`trendingScore`、`lastModified` 可作为热度和新鲜度信号。
- `agents-radar/src/hf.ts` 使用 `https://huggingface.co/api/models`，按近期 likes 抓 trending models。

P1 建议：

- Models/Datasets/Spaces 优先走官方 API。
- Papers/Trending 若官方 API 覆盖不足，可参考 RSSHub 路由或页面解析，但必须保存 snapshot。

### 5.5 Newsletter / AI 新闻源

相关仓库：

- `DIYgod/RSSHub`
- `duanyytop/agents-radar`
- `LearnPrompt/ai-news-radar`
- `sansan0/TrendRadar`

策略结论：

- TLDR AI、AIBase、LearnPrompt 等可作为 P1 的辅助聚合源，但不能替代原始官方源。
- Newsletter 如果有 RSS，就按 RSS 入 raw；如果只有邮件，应先进入 mailbox/newsletter raw source，再解析正文。
- `agents-radar` 展示了 GitHub Actions/定时 digest 的轻量管线；`TrendRadar` 展示了“多平台热点 + RSS + AI 分析 + 通知”的产品方向，但工程质量和数据源策略需要单独验证。

P1 建议：

- 聚合源只作为候选线索源，Evidence Card 优先补官方原始链接。
- 对 newsletter 保留邮件原文/网页归档链接，避免只存摘要。

### 5.6 中文竞品源

相关仓库与来源：

- `DIYgod/RSSHub` 的 AIBase 相关 route。
- `LearnPrompt/ai-news-radar` 的中文 AI 新闻整理脚本。
- `sansan0/TrendRadar` 的中文热点/RSS/AI 分析产品结构。
- `NanmiCoder/MediaCrawler` 的中文社媒多平台采集结构。

策略结论：

- 中文站适合作为“中文用户关心什么”的辅助信号。
- 不能把中文聚合站作为事实源的唯一证据，尤其是工具发布、模型发布、融资、政策等事件。
- P1 应在 Evidence Card 中标注“原始源 / 聚合源 / 社区源”的来源等级。

### 5.7 中文社媒采集参考：MediaCrawler

仓库：`NanmiCoder/MediaCrawler`

链接：https://github.com/NanmiCoder/MediaCrawler

源码观察：

- 截至 2026-06-03，GitHub API 显示 stars 约 50,622，最近 push 为 2026-05-29，主要语言为 Python。
- `main.py` 中 `CrawlerFactory.CRAWLERS` 将 `xhs`、`dy`、`ks`、`bili`、`wb`、`tieba`、`zhihu` 映射到各平台 crawler；当前不包含 X/Twitter、Facebook、Reddit。
- `config/base_config.py` 暴露 `PLATFORM`、`LOGIN_TYPE`、`COOKIES`、`CRAWLER_TYPE`、`ENABLE_IP_PROXY`、`SAVE_LOGIN_STATE`、`SAVE_DATA_OPTION`、评论采集和并发等配置。
- `base/base_crawler.py` 抽象了 `AbstractCrawler`、`AbstractLogin`、`AbstractStore`、`AbstractApiClient`。
- `media_platform/*/core.py` 普遍使用 Playwright 创建浏览器上下文，支持普通浏览器或 CDP 模式，并在多平台中注入 `libs/stealth.min.js`。
- `media_platform/*/client.py` 按平台封装私有 endpoint、签名参数、cookie 更新、评论/详情/搜索请求和重试。
- `media_platform/*/login.py` 支持二维码、手机号、cookie 登录态。
- `proxy/proxy_ip_pool.py` 支持快代理、豌豆代理和静态代理。

能力边界：

- 能覆盖小红书、抖音、快手、B 站、微博、百度贴吧、知乎的搜索、指定内容、作者主页、评论/二级评论等场景。
- 不能直接满足 X/Twitter 或 Facebook 采集；后续若有人试图“照着扩展 X/Facebook”，必须先经过合规、账号风险和数据范围评审。
- 它更像中文社媒采集实验框架，不是 AI World Radar P1 的稳定信源采集框架。

许可证与风险：

- LICENSE 为 `NON-COMMERCIAL LEARNING LICENSE 1.1`，限制非商业学习使用，明确不得用于大规模爬虫或影响平台运营；AI World Radar 不应把它作为生产依赖。
- 项目核心依赖登录态、cookie、二维码/手机号登录、浏览器自动化、签名参数、代理池和平台风控处理，和 P1 “无登录、低风险、可持续、可回源”的原则冲突。
- README 与源码均带有学习/研究用途提示；后续 Agent 不应把它解读为可直接上线的合规方案。

可借鉴点：

- 多平台 adapter/factory 结构：`PLATFORM -> crawler` 的注册方式可作为 Source Registry 的反面与正面参考。
- 分层接口：crawler、login、api client、store 分离，有助于 AI World Radar 设计 `source adapter + fetcher + normalizer + store`。
- 采集模式拆分：`search | detail | creator` 可映射到 AI World Radar 的 `list | detail | profile | comments` collector mode。
- 存储选项：json/jsonl/csv/sqlite/db/postgres/excel 的分层思路可参考，但 P1 应优先 Raw Snapshot + Raw Item 数据库，不需要 excel/wordcloud 等展示型输出。
- 风险配置显式化：登录类型、cookie、代理、评论深度、最大采集数应在 AI World Radar 的 adapter manifest 中作为风险字段，而不是隐藏在代码里。

阶段建议：

- P1：不建议接入，也不建议作为依赖。
- P1.5：只可借鉴 adapter、store、source health、评论字段设计；不得引入登录/cookie/代理/stealth 采集。
- P2：可作为“中文社媒热度实验室”的源码参考，仅限授权、小规模、隔离环境，并需单独合规评审。
- 不建议：任何需要账号池、绕过登录、抓取私密内容或大规模中文社媒采集的方案。

## 6. 典型仓库分析

### 6.1 仓库学习链接

以下链接用于后续自己学习源码。更详细的“如何精准爬取目标信息”的策略拆解，见同目录新增报告：[GitHub爬虫精准采集策略补充调研.md](GitHub爬虫精准采集策略补充调研.md)。

| 分组 | 仓库 | GitHub 链接 | 建议重点看 |
|---|---|---|---|
| P1 稳定源 | feedparser | https://github.com/kurtmckee/feedparser | `feedparser/api.py`, `feedparser/http.py` |
| P1 稳定源 | RSSHub | https://github.com/DIYgod/RSSHub | `lib/registry.ts`, `lib/routes/*` |
| P1 稳定源 | Miniflux | https://github.com/miniflux/v2 | `internal/reader/*`, `internal/storage/entry.go` |
| P1 稳定源 | Huginn | https://github.com/huginn/huginn | `app/models/agents/rss_agent.rb`, `website_agent.rb` |
| P1 稳定源 | changedetection.io | https://github.com/dgtlmoon/changedetection.io | `changedetectionio/worker.py`, processors |
| P1 稳定源 | HackerNews/API | https://github.com/HackerNews/API | 官方 Firebase API 文档 |
| P1 稳定源 | node-hnapi | https://github.com/cheeaun/node-hnapi | `lib/hnapi.js`, `lib/cache.js` |
| P1 稳定源 | huggingface_hub | https://github.com/huggingface/huggingface_hub | `src/huggingface_hub/hf_api.py` |
| P1 稳定源 | agents-radar | https://github.com/duanyytop/agents-radar | `src/github.ts`, `src/hf.ts`, `src/hn.ts` |
| P1.5 热度源 | PRAW | https://github.com/praw-dev/praw | `praw/models/reddit/subreddit.py`, `listing/generator.py` |
| P1.5 热度源 | prawcore | https://github.com/praw-dev/prawcore | `prawcore/rate_limit.py`, `sessions.py` |
| P1.5 热度源 | asyncpraw | https://github.com/praw-dev/asyncpraw | async PRAW modules |
| P1.5 热度源 | redditwarp | https://github.com/Pyprohly/redditwarp | `redditwarp/core/rate_limited_SYNC.py` |
| P1.5 热度源 | youtube/api-samples | https://github.com/youtube/api-samples | `python/search.py`, `comment_threads.py`, `captions.py` |
| P1.5 热度源 | google-api-python-client | https://github.com/googleapis/google-api-python-client | `googleapiclient/discovery.py`, `http.py` |
| P1.5 热度源 | yt-dlp | https://github.com/yt-dlp/yt-dlp | `yt_dlp/extractor/youtube/_video.py`, `_tab.py`, `_search.py` |
| P1.5 热度源 | YouTube.js | https://github.com/LuanRT/YouTube.js | `src/Innertube.ts`, `src/core/Session.ts` |
| P1.5 热度源 | youtube-transcript-api | https://github.com/jdepoix/youtube-transcript-api | `youtube_transcript_api/_api.py`, `_transcripts.py` |
| P1.5 热度源 | youtube-comment-downloader | https://github.com/egbertbouman/youtube-comment-downloader | `youtube_comment_downloader/downloader.py` |
| P1.5 热度源 | github-trending-api | https://github.com/huchenme/github-trending-api | `src/functions/utils/fetch.js` |
| P1.5 热度源 | go-trending | https://github.com/andygrunwald/go-trending | `trending.go` |
| P1.5 热度源 | github-trending-repos | https://github.com/vitalets/github-trending-repos | `scripts/helpers/trends.js` |
| P2 / 高风险 | tweepy | https://github.com/tweepy/tweepy | `tweepy/client.py`, `tweepy/pagination.py` |
| P2 / 高风险 | twarc | https://github.com/DocNow/twarc | `src/twarc/client2.py`, decorators |
| P2 / 高风险 | twscrape | https://github.com/vladkens/twscrape | `twscrape/api.py`, `accounts_pool.py` |
| P2 / 高风险 | snscrape | https://github.com/JustAnotherArchivist/snscrape | `snscrape/modules/twitter.py`, `reddit.py`, `facebook.py` |
| P2 / 高风险 | ntscraper | https://github.com/bocchilorenzo/ntscraper | `ntscraper/nitter.py` |
| P2 / 高风险 | nitter | https://github.com/zedeus/nitter | service code |
| P2 / 高风险 | redlib | https://github.com/redlib-org/redlib | `src/client.rs`, `oauth.rs`, `post.rs` |
| P2 / 高风险 | facebook-sdk | https://github.com/mobolic/facebook-sdk | `facebook/__init__.py` |
| P2 / 高风险 | python-facebook | https://github.com/sns-sdks/python-facebook | `pyfacebook/api/graph.py` |
| P2 / 高风险 | facebook-python-business-sdk | https://github.com/facebook/facebook-python-business-sdk | Business SDK modules |
| P2 / 高风险 | facebook-scraper | https://github.com/kevinzg/facebook-scraper | `facebook_scraper.py`, `extractors.py` |
| P2 / 高风险 | MediaCrawler | https://github.com/NanmiCoder/MediaCrawler | `main.py`, `config/base_config.py`, `media_platform/*` |
| 通用框架 | Crawlee | https://github.com/apify/crawlee | `packages/basic-crawler/*` |
| 通用框架 | Firecrawl | https://github.com/firecrawl/firecrawl | API controller/types |
| 通用框架 | Crawl4AI | https://github.com/unclecode/crawl4ai | `crawl4ai/async_webcrawler.py` |
| 通用框架 | ScrapeGraphAI | https://github.com/ScrapeGraphAI/Scrapegraph-ai | `scrapegraphai/graphs/*`, `nodes/*` |
| 通用框架 | Scrapy | https://github.com/scrapy/scrapy | downloader middlewares, retry |

| 仓库 | stars / 更新时间 / 语言 | 解决的问题 | 关键源码路径 | 采集方式 | 登录/Token/代理 | 稳定性处理 | 借鉴点 | 不适合点 | 阶段 |
|---|---:|---|---|---|---|---|---|---|---|
| `DIYgod/RSSHub` | 44,455 / 2026-06-03 / TypeScript | 把各站点转换为 RSS | `lib/registry.ts`, `lib/routes/*` | RSS/HTML/API route | 多数 public 源无需登录，部分 route 可 token | route cache，中间件，统一输出 | source namespace + adapter | AGPL、全量依赖重 | P1 参考 |
| `kurtmckee/feedparser` | 2,370 / 2026-06-01 / Python | RSS/Atom/JSON Feed 解析 | `feedparser/api.py`, `http.py` | RSS/Atom/JSON Feed | 无 | ETag/modified 参数、bozo 异常 | P1 feed parser | 不负责调度/存储 | P1 |
| `huggingface/huggingface_hub` | 3,648 / 2026-06-03 / Python | Hugging Face 官方 API | `src/huggingface_hub/hf_api.py` | API | public 可无 token | http backoff、cache、ETag | HF models/datasets/spaces | papers/trending 仍需验证 | P1 |
| `praw-dev/praw` | 4,140 / 2026-06-01 / Python | Reddit API wrapper | `praw/reddit.py`, `praw/models/listing/generator.py` | 官方 API | client_id/token/read-only auth | listing cursor、rate limit | Reddit 热度源 | P1 不必接入社区 | P1.5 |
| `praw-dev/prawcore` | 配套 / 2026-06-01 / Python | Reddit HTTP core | `prawcore/sessions.py`, `rate_limit.py` | API | token | retry、x-ratelimit headers、429 | rate limit 抽象 | 只适合 Reddit | P1.5 |
| `tweepy/tweepy` | 11,164 / 2025-07-11 / Python | X 官方 API wrapper | `tweepy/client.py`, `pagination.py` | 官方 API | bearer/OAuth | wait_on_rate_limit、pagination token | 合规 API 模式 | 成本/额度/政策 | P1.5/P2 |
| `DocNow/twarc` | 1,394 / 2025-10-31 / Python | X 官方 API 归档工具 | `src/twarc/client2.py`, `decorators2.py`, `utils/deduplicate.py` | 官方 API | bearer/OAuth | rate limit decorator、pagination、compliance | 归档/hydration/dedup | API 成本与权限 | P1.5 |
| `vladkens/twscrape` | 2,444 / 2026-05-23 / Python | X 非官方采集 | `accounts_pool.py`, `account.py`, `api.py` | 非官方 API/cookie | 账号、cookie、proxy | SQLite locks、stats、active | source health 思路 | 账号/ToS 风险高 | 不建议 |
| `JustAnotherArchivist/snscrape` | 5,393 / 2023-11-15 / Python | 多社交平台 scraper | `base.py`, `modules/twitter.py`, `modules/reddit.py` | HTML/非官方 API | guest token/proxy 可选 | retry/backoff、token block | retry/backoff | X/Facebook 稳定性差 | 不建议/P1.5 参考 |
| `bocchilorenzo/ntscraper` | 259 / 2025-05-24 / Python | Nitter HTML scraper | `ntscraper/nitter.py` | Nitter HTML | 无 X 登录，依赖实例 | 实例健康检查、失败换实例 | instance health | 公开实例不稳定 | 不建议 |
| `yt-dlp/yt-dlp` | 167,629 / 2026-05-25 / Python | 视频元数据/下载提取 | `yt_dlp/extractor/youtube/_video.py` | HTML/Innertube/多协议 | 可 cookie/proxy | extractor tests、cache | 字段覆盖完整 | 太重，目标不是采集系统 | P1.5/P2 |
| `googleapis/google-api-python-client` | 元数据未列入主表 / Python | Google 官方 API client | `googleapiclient/discovery.py`, `http.py` | 官方 API | API key/OAuth | discovery/http retry | YouTube Data API | 配额和 key 管理 | P1.5 |
| `youtube/api-samples` | 约 6,000 / 2018-04 / 多语言 | YouTube Data API 样例 | `python/search.py`, `python/comment_threads.py`, `python/captions.py` | 官方 API | API key/OAuth | pageToken/nextPageToken | 官方字段模型 | 样例老、需配额 | P1.5 |
| `LuanRT/YouTube.js` | 约 5,000 / 2026-05-29 / TypeScript | InnerTube 客户端 | `dist/src/Innertube.js`, `core/Session.js` | 非官方 InnerTube | 可 OAuth/cookie | continuation、parser classes | Node 侧实验 | 内部 API 风险 | P1.5 |
| `youtube-transcript-api` | 7,678 / 2026-05-19 / Python | YouTube 字幕提取 | `_api.py`, `_transcripts.py`, `proxies.py` | 非官方字幕接口 | 可 proxy/cookie | 429 -> IpBlocked、细分异常 | transcript enrichment | 不适合广域主采集 | P1.5/P2 |
| `youtube-comment-downloader` | 1,225 / 2025-08-29 / Python | YouTube 评论采集 | `downloader.py` | Innertube/HTML | 无登录，可能需代理 | continuation、retry sleep | 评论热度补充 | 非官方接口 | P2 |
| `mobolic/facebook-sdk` | 2,788 / 2024-08-02 / Python | Facebook Graph API SDK | `facebook/__init__.py` | 官方 API | access_token | paging next、GraphAPIError | 合规路径 | 数据范围受限 | P2 可选 |
| `sns-sdks/python-facebook` | 约 378 / 2026-02 / Python | Graph API wrapper | `pyfacebook/api/graph.py`, `resource/page.py` | 官方 API | app/token/权限 | cursor paging、rate-limit sleep | 授权场景 | 不支持匿名情报 | P2 |
| `facebook-python-business-sdk` | 约 1,500 / 2026-06-02 / Python | Meta Business API SDK | business SDK modules | 官方 API | business token/app review | 官方 SDK | 商业数据授权 | 不是公开帖子采集 | P2+ |
| `kevinzg/facebook-scraper` | 3,199 / 2024-06-22 / Python | Facebook 页面/帖子 HTML | `facebook_scraper.py`, `extractors.py`, `page_iterators.py` | mobile/mbasic HTML | cookie/login/proxy | next_url、LoginRequired | 风险样本 | 账号/ToS/稳定性风险高 | 不建议 |
| `NanmiCoder/MediaCrawler` | 50,622 / 2026-05-29 / Python | 中文社媒多平台采集 | `main.py`, `config/base_config.py`, `base/base_crawler.py`, `media_platform/*/core.py`, `media_platform/*/client.py`, `media_platform/*/login.py`, `proxy/proxy_ip_pool.py` | Playwright/browser + 非官方接口/签名 | 二维码/手机号/cookie、登录态缓存、可选代理 | retry、登录检测、代理刷新、采集上限 | adapter factory、crawler/login/client/store 分层、search/detail/creator 模式 | 不支持 X/Facebook；非商业学习许可证；账号/ToS/风控风险高 | P2 研究参考，不进 P1 |
| `Pyprohly/redditwarp` | 58 / 2024-07-01 / Python | Reddit API wrapper | `redditwarp/core/rate_limited_SYNC.py` | 官方 API | OAuth | token bucket | rate budget | 生态小 | P2 参考 |
| `redlib-org/redlib` | 3,371 / 2026-04-24 / Rust | Reddit 替代前端 | `src/client.rs`, `oauth.rs`, `post.rs` | Reddit JSON/OAuth | token daemon | cache、canonical path | parser/canonicalization | mobile spoof 风险 | 不建议 |
| `huchenme/github-trending-api` | 823 / 2023-01-06 / JavaScript | GitHub Trending API 化 | `src/functions/utils/fetch.js` | HTML + Cheerio | 无 | 无强重试 | selector 示例 | 页面变动风险 | P1 第二批 |
| `andygrunwald/go-trending` | 146 / 2026-04-01 / Go | GitHub Trending Go parser | `trending.go` | HTML + goquery | 无 | 无强重试 | 字段抽取 | selector 易碎 | P1 第二批 |
| `cheeaun/node-hnapi` | 347 / 2026-02-15 / JavaScript | HN API 封装 | `lib/hnapi.js`, `lib/cache.js` | Firebase/API/页面混合 | 无 | memory/Redis cache | HN cache/endpoint | HTML 部分不必依赖 | P1 |
| `duanyytop/agents-radar` | 786 / 2026-06-03 / TypeScript | AI ecosystem daily digest | `src/github.ts`, `src/hf.ts`, `src/hn.ts` | API | GitHub token 可选/推荐 | 时间窗口、分页、失败返回 | P1 digest pipeline | 不是通用采集内核 | P1 参考 |
| `dgtlmoon/changedetection.io` | 31,857 / 2026-06-03 / Python | 网页变更监控 | `worker.py`, fetchers, processors | HTTP/browser | 可配置 | snapshot、diff、last_error、watch health | raw snapshot/diff | 关注变化不是事件 | P1/P1.5 参考 |
| `apify/crawlee` | 23,643 / 2026-06-02 / TypeScript | 大规模 crawler 框架 | `packages/basic-crawler/src/internals/basic-crawler.ts` | HTTP/browser | proxy/session 可配 | requestQueue、retry、sessionPool、failed handler | P1.5 browser worker | P1 core 太重 | P1.5 |
| `firecrawl/firecrawl` | 127,948 / 2026-06-03 / TypeScript | AI-friendly web crawl API | `apps/api/src/controllers/v2/types.ts` | API/browser/extract | 服务化 | cache、rawHtml、markdown、screenshot | output contract | 不应绑定核心依赖 | P1.5/P2 |
| `unclecode/crawl4ai` | 67,677 / 2026-06-01 / Python | LLM-friendly crawler | `crawl4ai/async_webcrawler.py` | browser/HTTP/LLM | 可配 | CrawlResult、cache mode | markdown/extraction 边界 | 不能替代原始证据 | P1.5 |
| `huginn/huginn` | 49,395 / 2026-06-03 / Ruby | agent/workflow 监控系统 | `app/models/agent.rb`, `rss_agent.rb`, `website_agent.rb` | RSS/API/page | 可配 | schedule、memory、expected update | source health/workflow | P1 太重 | P1 参考/P2 |

## 7. 源码策略对比

| 策略 | 稳定性 | 合规风险 | 工程成本 | 适合来源 | AI World Radar 建议 |
|---|---|---|---|---|---|
| 官方 RSS/Atom/JSON Feed | 高 | 低 | 低 | 官方博客、新闻、newsletter | P1 主路径 |
| 官方 API | 高 | 低到中 | 中 | GitHub、HN、HF、Reddit、YouTube | P1/P1.5，视 API 额度 |
| 稳定 HTML 页面解析 | 中 | 中 | 中 | GitHub Trending、部分博客、AIBase | P1 第二批，必须快照和 selector test |
| RSSHub route 复用/参考 | 中到高 | 取决于 route | 中 | 公开网站转换 RSS | P1 参考，不整体绑定 |
| Browser automation | 中 | 中到高 | 高 | JS 渲染页面、少量高价值源 | P1.5 兜底，不进 P1 主路径 |
| 非官方 API / 私有 endpoint | 低到中 | 高 | 高 | X、YouTube comments、Facebook HTML | 不进 P1；谨慎 P1.5/P2 |
| cookie 登录 / 账号池 / 代理 | 低 | 高 | 高 | X、Facebook、中文社媒 | 不建议 |
| LLM extraction fallback | 中 | 低到中 | 中到高 | schema drift、复杂页面摘要 | P1.5/P2；不能作为唯一证据 |

## 8. 推荐给 AI World Radar 的采集架构

### 8.1 Source Registry

建议字段：

```yaml
source_id: openai_news
display_name: OpenAI News
platform: openai
source_kind: official_blog
priority_stage: P1
collector_mode: rss
entrypoints:
  - https://openai.com/news/rss.xml
auth_profile: none
schedule:
  interval_minutes: 60
rate_limit_policy:
  rpm: 30
fetch_policy:
  timeout_seconds: 20
  user_agent_profile: default
adapter_id: openai_news_rss
parser_profile: feedparser
dedupe_keys:
  - guid
  - canonical_url
  - title_published_date
snapshot_policy:
  store_body: true
  store_headers: true
  ttl_days: 90
health_policy:
  expected_update_period_hours: 72
  circuit_breaker: true
legal_risk: low
owner: system
status: active
last_validated_at: 2026-06-03
```

### 8.2 Adapter Manifest

每个 adapter 都应声明能力，而不是把逻辑藏在代码里：

```yaml
adapter_id: github_trending
version: 1
stage: P1_second_batch
modes:
  - page
inputs:
  language: optional
  since: daily
outputs:
  raw_item_schema: raw_item.v1
fetch:
  primary: page
  url_template: https://github.com/trending/{language}?since={since}
retry:
  max_attempts: 3
  backoff: exponential_jitter
rate_limit:
  key: source
  rpm: 10
snapshot:
  store_body: true
  store_headers: true
  ttl_days: 180
normalize:
  mapper: github_trending_v1
dedupe:
  keys:
    - repo_full_name
    - date
evidence:
  builders:
    - source_metadata
    - popularity_signal
health:
  selector_test: true
  success_rate_window: 7d
  circuit_breaker: true
risk:
  legal: medium
  stability: medium
```

### 8.3 Fetch Mode 分层

```text
rss/api
  -> P1 主路径

page_html
  -> P1 第二批，要求 snapshot + selector test

browser
  -> P1.5 高价值兜底，不默认启用

llm_fallback
  -> P1.5/P2 抽取辅助，不能替代 raw evidence

unofficial_api / cookie_login
  -> 默认不进产品主链路
```

### 8.4 Raw Item

Raw Item 表示“抓到了什么”，建议字段：

```yaml
raw_item_id: string
source_id: string
adapter_id: string
adapter_version: string
url: string
canonical_url: string
title: string
author: string
published_at: datetime
fetched_at: datetime
raw_snapshot_id: string
http_status: number
headers_hash: string
content_hash: string
dedupe_key: string
raw_metadata:
  score: number
  comments_count: number
  likes: number
  downloads: number
  platform_specific: object
parse_status: success | partial | failed
parse_error_class: string
```

### 8.5 Evidence Card

Evidence Card 表示“为什么可信/为什么值得看”，建议字段：

```yaml
evidence_card_id: string
claim: string
source_level: official | platform | community | aggregator
source_url: string
quote_or_excerpt: string
entities:
  - OpenAI
  - GPT-5
event_time: datetime
evidence_time: datetime
heat_signals:
  hn_points: number
  reddit_score: number
  github_stars_delta: number
  hf_likes: number
confidence: high | medium | low
raw_item_ids:
  - string
conflict_evidence_ids:
  - string
recommended_action: publish | hold | enrich | discard
```

### 8.6 错误分类

建议统一错误枚举：

- `transient_network`
- `rate_limited`
- `blocked_or_antibot`
- `auth_failed`
- `robots_disallowed`
- `empty_content`
- `parse_schema_mismatch`
- `source_contract_changed`
- `duplicate`
- `llm_uncertain`
- `internal_bug`

### 8.7 Source Health

每个 source 维护：

- `last_success_at`
- `last_failure_at`
- `consecutive_failures`
- `success_rate_24h`
- `success_rate_7d`
- `parse_success_rate`
- `median_latency_ms`
- `freshness_lag_minutes`
- `block_rate`
- `last_error_class`
- `health_status: green | yellow | red`

当 source 进入 red：

- 暂停 browser/LLM 高成本 fallback。
- 保留低频健康探测。
- 进入维护队列，提示 adapter 可能需要更新。

## 9. P1 / P1.5 / P2 分阶段建议

### P1

目标：稳定、可回源、低风险地采集首批 AI 事件候选。

建议做：

- Source Registry。
- Adapter Manifest。
- RSS/API/page fetcher。
- Raw Snapshot Store。
- Raw Item Normalizer。
- Evidence Card Builder。
- Dedupe 和 source health。
- P1 信息源：OpenAI、Anthropic、DeepMind、NVIDIA、GitHub Changelog、HN、HF、TLDR AI、AIBase。

暂不做：

- X/Facebook 非官方采集。
- YouTube 评论采集。
- MediaCrawler 或类似中文社媒登录态采集。
- 大规模 browser worker。
- 代理池、账号池、cookie 登录。
- AI follow-up assistant。

### P1.5

目标：引入热度信号和候选池，增强“AI 圈正在讨论什么”。

建议做：

- Reddit 官方 API。
- YouTube Data API。
- GitHub Trending 每日快照。
- Hugging Face Papers/Trending。
- Browser worker 作为少量源的 fallback。
- LLM extraction fallback，但必须绑定 raw snapshot。
- source health dashboard。
- candidate event pool。
- MediaCrawler 只作为多平台 adapter 和风险字段设计参考，不作为运行时依赖。

### P2

目标：更完整的情报系统和交互能力。

建议做：

- X 官方 API 或授权数据源。
- Facebook Graph API 授权页面。
- 中文社媒热度实验室；若参考 MediaCrawler，只能在授权、小规模、隔离环境中研究。
- AI follow-up assistant。
- 个性化订阅。
- 跨源冲突检测。
- 可视化 source/workflow 管理。
- adapter marketplace 或自定义 source。

默认仍不建议：

- 非授权账号池。
- 绕过登录或反爬。
- 抓取私密内容。
- 用 LLM 生成无法回源的事实。

## 10. 风险清单

| 风险 | 影响 | 典型来源 | 处理建议 |
|---|---|---|---|
| ToS / 合规风险 | 账号、服务、法律风险 | X 非官方 API、Facebook HTML | 不进 P1；优先官方 API/授权 |
| 登录/cookie 风险 | 账号封禁、泄露、维护成本 | twscrape、facebook-scraper | 禁止产品主链路使用 |
| 非商业许可证风险 | 不能作为生产依赖 | MediaCrawler | 只做源码策略参考，不能直接集成 |
| 反爬/封禁风险 | 高失败率、不稳定 | YouTube comments、X、Facebook | 限制在 P1.5/P2 兜底 |
| 中文社媒风控风险 | 登录失败、验证码、账号限制、数据不稳定 | MediaCrawler、小红书/抖音/微博等 | 不进 P1；P2 必须授权、小规模、隔离 |
| 页面结构漂移 | parse fail、误采 | GitHub Trending、AIBase 页面 | selector test + snapshot + health |
| API 额度风险 | 数据缺口、成本 | YouTube Data API、X API | 配额监控 + 低频策略 |
| 聚合源事实污染 | 二手信息误传 | TLDR AI、AIBase、中文聚合站 | Evidence Card 补原始源 |
| LLM 幻觉 | 事实错配 | LLM extraction | LLM 不能作为唯一证据 |
| 重复内容 | 事件卡重复 | RSS、多源转载 | canonical_url + title/date + content_hash |
| 热议/事实混淆 | 把观点当新闻 | Reddit/HN/comments | source_level 标注，Quality Gate |

## 11. 后续待验证问题

1. OpenAI、Anthropic、DeepMind、NVIDIA 当前是否都有稳定 RSS；没有 RSS 的页面 selector 如何设计。
2. AIBase 是否有稳定 RSS 或公开列表 API；若只有 HTML，selector test 如何覆盖。
3. TLDR AI 是否可通过公开 RSS、newsletter archive 或邮件入口稳定采集。
4. Hugging Face Daily Papers 是否完全可由官方 API 覆盖，还是需要 RSSHub/page adapter。
5. GitHub Trending 是否进入 P1 第二批还是 P1.5；如果进入 P1，是否接受每日一次快照。
6. P1 Raw Snapshot 存储用数据库、对象存储还是本地文件；保留周期如何定。
7. Evidence Card 的 quote/excerpt 是否需要保存原文短摘，如何避免版权和过度引用风险。
8. 是否需要 source health 管理页，还是 P1 先用日志/表格即可。
9. 未来 X/Reddit/YouTube 热度信号如何与官方源事实事件做聚合，不让热度压过可信度。
10. 若未来引入中文社媒热度信号，哪些平台有官方/授权路径；MediaCrawler 只能作为架构参考，不能作为默认实现。
11. 是否需要为高风险源设单独的“research-only”运行环境，隔离生产发布链路。
