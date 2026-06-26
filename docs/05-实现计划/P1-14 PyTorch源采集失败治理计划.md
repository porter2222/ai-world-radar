# P1-14 PyTorch源采集失败治理计划

更新时间：2026-06-26

## 1. 目标

P1-14 的目标是单独治理 `pytorch_blog` 官方源在真实生产采集路径中的 HTTP `403 Forbidden` 问题，让 PyTorch Blog RSS 能继续作为 `official_feeds` 的有效来源进入 `source_signals`。

本阶段只修复 PyTorch 官方源采集失败，不扩大为全源爬虫系统重构。

## 2. 当前现象

历史验收记录中，P1-11、P1-12、P1-13 多次记录 `pytorch_blog` 在 `daily_all` 真实采集中失败：

```text
source_key=pytorch_blog
url=https://pytorch.org/blog/feed.xml
error=403 Forbidden
```

本轮在独立分支 `codex/pytorch-source-fix` 复现到同样问题：

```powershell
.\.venv\Scripts\python.exe scripts\collect_source_signals.py `
  --database-url "sqlite+pysqlite:///scratch/pytorch_source_fix_before.sqlite" `
  --create-schema-for-smoke `
  --source official_feeds `
  --official-profile pytorch_blog `
  --official-limit 3 `
  --lookback-hours 10000 `
  --continue-on-source-error
```

实际输出：

```json
{
  "status": "succeeded",
  "source_keys": [],
  "sources_count": 0,
  "signals_count": 0,
  "failed_sources_count": 1,
  "failed_sources": [
    {
      "source_key": "pytorch_blog",
      "error": "Client error '403 Forbidden' for url 'https://pytorch.org/blog/feed.xml'"
    }
  ]
}
```

注意：脚本总状态是 `succeeded`，是因为开启了 `--continue-on-source-error`，但 PyTorch 单源实际没有采集成功。

## 3. 根因调查

同一个 PyTorch feed URL 的客户端对比结果如下。

| 客户端路径 | 结果 | 说明 |
| --- | --- | --- |
| 当前 `official_news.fetch_official_news()` | `HTTPStatusError 403` | 当前生产 collector 失败 |
| `httpx.get(..., follow_redirects=True)` | `403 text/html` | 直接复现当前 collector 的失败 |
| `urllib.request.urlopen()` | `200 application/rss+xml` | Python 标准库可成功获取 RSS |
| `curl.exe -L -I` | `301 -> 200 application/rss+xml` | URL 本身有效，最终跳转到 `/blog/feed/` |
| `httpx` 直接访问 `/blog/feed/` | `403 text/html` | 不是单纯重定向 URL 配置错误 |

当前判断：

> PyTorch feed URL 本身可访问，问题不在 profile 地址；失败集中发生在当前 `httpx` 请求路径上，更像 PyTorch/Pantheon/CDN 对 `httpx` 请求栈的拦截。更换为 `/blog/feed/` 不能解决，因为 `httpx` 直接访问最终地址仍然返回 403。

## 4. 方案取舍

### 4.1 选择方案

采用最小 source 级 fallback：

1. 默认仍使用现有 `httpx` collector，不改变其他官方源主路径。
2. 仅当官方源 HTTP 请求出现 `403 Forbidden` 时，使用 Python 标准库 `urllib.request` 重试一次。
3. fallback 成功后仍复用现有 RSS/Atom/HTML 解析函数，不新增解析链路。
4. 在 `OfficialNewsEntry` 中增加可选 `fetch_metadata`，记录 `fetch_client`、`fallback_used`、`fallback_reason` 等信息。
5. source adapter 将该 metadata 写入 `SourceSignal.metadata`，后续验收和后台排查可看到 fallback 是否发生。

### 4.2 不选择的方案

- 不禁用 `pytorch_blog`。
- 不从 `daily_all` 移除 `pytorch_blog`。
- 不把 PyTorch 改成 fixture 或 mock 通过。
- 不引入 Playwright、代理池、完整爬虫框架。
- 不把所有 official source 全量切到 `urllib`，避免破坏已有稳定源。
- 不只修改 User-Agent 后声称修复，因为本轮证据显示同一 User-Agent 下 `urllib` 可 200、`httpx` 仍 403，客户端栈差异比普通 UA 更关键。

## 5. 影响范围

### 修改文件

- `apps/worker/worker/collectors/official_news.py`
- `apps/worker/worker/sources/official_news_source.py`
- `apps/worker/tests/test_official_news_collector.py`

### 文档文件

- `docs/05-实现计划/P1-14 PyTorch源采集失败治理计划.md`
- `docs/05-实现计划/P1-14 PyTorch源采集失败治理计划.html`
- `docs/07-验收与运行/后端P1测试记录.md`
- `docs/00-项目总览/项目状态.md`
- `docs/00-项目总览/文档索引.md`
- `docs/README.md`

## 6. TDD 执行计划

### Task 1：计划与基线

- [x] 确认 worktree：`D:\AI World Radar-worktrees\pytorch-source-fix`
- [x] 确认分支：`codex/pytorch-source-fix`
- [x] 从 `D:\AI World Radar\.env` 同步真实 `.env` 到 worktree，且不提交。
- [x] 运行相关基线测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_official_news_collector.py tests/test_collect_source_signals_script.py -q
```

实际结果：

```text
22 passed in 49.50s
```

- [x] 复现当前 PyTorch 单源生产路径失败。

### Task 2：失败测试

- [ ] 在 `tests/test_official_news_collector.py` 增加测试：当 `httpx` 主请求返回 403，而 `urllib` fallback 返回 RSS XML 时，`fetch_official_news()` 应成功返回 PyTorch 条目。
- [ ] 测试断言返回条目包含 `fetch_metadata.fallback_used=True`。
- [ ] 测试断言 fallback 原因包含 `403`。
- [ ] 运行单测确认 RED，失败原因应是当前实现直接抛出 `HTTPStatusError` 或没有 fallback metadata。

### Task 3：最小实现

- [ ] 在 `official_news.py` 中增加内部 fallback fetch 函数。
- [ ] 只对 HTTP `403` 触发 fallback。
- [ ] fallback 使用 `urllib.request`，继续设置项目 User-Agent。
- [ ] 保持现有 `collect_from_feed_xml()` / `collect_from_news_html()` 解析逻辑。
- [ ] 给 `OfficialNewsEntry` 增加 `fetch_metadata`，并在 fallback 成功时写入。
- [ ] 在 `official_news_source.py` 中把 `fetch_metadata` 合并到 `SourceSignal.metadata`。

### Task 4：回归测试

必须运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_official_news_collector.py -v
.\.venv\Scripts\python.exe -m pytest tests/test_collect_source_signals_script.py -v
```

如改动影响 source adapter，还需要运行相关源映射测试。

### Task 5：真实 PyTorch 单源验收

不跑全源，不跑 `daily_all`，不跑完整 daily pipeline。只跑 PyTorch 单源生产入口：

```powershell
.\.venv\Scripts\python.exe scripts\collect_source_signals.py `
  --database-url "sqlite+pysqlite:///scratch/pytorch_source_fix_after.sqlite" `
  --create-schema-for-smoke `
  --source official_feeds `
  --official-profile pytorch_blog `
  --official-limit 5 `
  --lookback-hours 10000 `
  --continue-on-source-error
```

验收通过标准：

- stdout JSON 中不再出现 `pytorch_blog` 的 403 failed source。
- `source_keys` 包含 `pytorch_blog`。
- `signals_count > 0`。
- 临时 SQLite 中存在 `source_key=pytorch_blog` 的 `source_signals`。
- 至少一条 signal metadata 中记录 fallback 发生过。

如果真实 RSS 条目因发布时间窗口未写入，则必须额外运行真实 fetch/parse smoke，证明真实 PyTorch RSS 已成功拉取并解析出条目。

## 7. 验收记录要求

最终必须在 `docs/07-验收与运行/后端P1测试记录.md` 记录：

- 测了什么。
- 用什么数据测。
- 命令是什么。
- 真实输出是什么。
- 是否真实网络。
- 是否写库。
- 是否使用临时 SQLite。
- 哪些没有测。

## 8. 非目标

本阶段不处理：

- `anthropic_news` SSL EOF。
- 全源失败治理体系。
- source 禁用/降级后台管理。
- Windows 定时任务。
- Redis / 队列 / 调度守护。
- DailyEdition。
- 前端页面。
- 真实 LLM pipeline。

## 9. 提交计划

建议提交顺序：

1. `docs: plan pytorch source fetch recovery`
2. `fix(worker): add pytorch official feed fallback`
3. `docs: record pytorch source acceptance`

最终不合并 main，只输出验收结果并等待用户确认。
