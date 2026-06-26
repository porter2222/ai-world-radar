# AI World Radar 配置体系规范化设计

日期：2026-06-26
分支：`codex/config-system`
工作区：`D:\AI World Radar-worktrees\config-system`

## 1. 背景

当前项目已经具备 FastAPI 产品接口、Next.js 公共前端、Python Worker 日常流水线、真实 LLM Agent 和 PostgreSQL 写入链路。随着首页时效窗口、首页展示数量、日常流水线采集窗口、selector batch size、每轮最多发布数量、未来定时运行时间等策略项增加，配置边界开始变得模糊。

现状中存在三类问题：

- `.env.example` 已经混入部分流水线策略，例如 `DAILY_PIPELINE_LOOKBACK_HOURS`、`DAILY_PIPELINE_MAX_SELECTED`。
- `DailyPipelineConfig.from_env()` 在 service 文件中直接读取 `os.getenv`，配置入口不统一。
- 首页展示窗口、前端请求数量等产品策略仍分散在 service 或前端调用处。

这次设计目标是建立 P1 阶段足够清晰、可测试、不过度设计的配置体系。

## 2. 决策

采用方案 2：统一 typed config，允许少量 env override。

`apps/worker/worker/config.py` 继续作为后端配置入口，但需要从单一 `Settings` 扩展为分层配置对象。`.env` 只保留环境相关、密钥相关、服务连接相关和少量本机运行模式相关配置，不再承载普通产品策略默认值。

本轮不引入 YAML / JSON 配置文件，不引入数据库配置表，不做后台配置页。

## 3. 配置分类

### 3.1 环境配置

环境配置描述“当前机器或当前部署环境如何运行项目”。这些配置允许放在 `.env`。

范围：

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_USER_AGENT`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DASHSCOPE_API_KEY`
- `DASHSCOPE_BASE_URL`
- `GITHUB_TOKEN`
- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_REQUEST_TIMEOUT_SECONDS`
- `AGENT_MODE`
- `AI_WORLD_RADAR_API_BASE_URL`

这些值可能因开发机、服务器、模型供应商、密钥和本地联调端口不同而变化。

### 3.2 产品策略配置

产品策略描述“产品希望如何展示内容”。这些默认值应进入 typed config，并被测试覆盖。

范围：

- 首页事件时间窗口，例如最近 12 小时或 48 小时。
- 首页默认展示数量。
- 首页最大展示数量。
- 首页是否允许历史兜底。
- 事件详情是否允许访问历史事件。

P1 当前原则：

- 首页列表只展示近期事件。
- 详情页仍可通过 slug 读取历史事件。
- public API 不暴露 `recent_hours` 给前端自由控制。
- 前端不应自行定义核心产品窗口。

### 3.3 日常流水线策略配置

流水线策略描述“每次生产链路如何运行”。这些默认值进入 typed config，少量本机调试项可被 `.env` 覆盖。

范围：

- `source_group`
- `lookback_hours`
- `candidate_lookback_hours`
- `selector_batch_size`
- `max_selected`
- `continue_on_source_error`
- `disable_agent_fallback`

P1 当前原则：

- 默认 source group 为 `daily_all`。
- 默认采集窗口为 8 小时。
- 默认候选聚合窗口为 48 小时。
- 默认 selector batch size 为 30。
- 默认每轮最多进入事件生产的 selected group 为 5。
- 默认真实运行不允许 Agent fallback 冒充真实成功。

### 3.4 调度策略配置

调度策略描述“什么时候自动运行”。这些默认值先进入 typed config，未来做后台配置时再迁移。

范围：

- 时区：`Asia/Shanghai`
- 日常流水线运行时间：`08:00`、`13:00`、`20:00`

P1 当前原则：

- 本轮只定义配置入口，不实现调度服务。
- 未来调度服务必须读取同一份 `SchedulerSettings`。
- 调度 stdout / stderr 和业务运行日志仍分离，业务日志继续写入 `runtime/daily-pipeline-*.log/jsonl`。

## 4. 后端设计

扩展 `apps/worker/worker/config.py`，新增分层 dataclass：

```python
@dataclass(frozen=True)
class RuntimeSettings:
    project_root: Path
    worker_dir: Path
    runtime_dir: Path
    database_url: str


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    request_timeout_seconds: int


@dataclass(frozen=True)
class ProductSettings:
    homepage_recent_hours: int
    homepage_default_limit: int
    homepage_max_limit: int
    homepage_min_recent_items: int
    homepage_backfill_days: int | None


@dataclass(frozen=True)
class DailyPipelineSettings:
    source_group: str
    lookback_hours: int
    candidate_lookback_hours: int
    selector_batch_size: int
    max_selected: int | None
    continue_on_source_error: bool
    disable_agent_fallback: bool


@dataclass(frozen=True)
class SchedulerSettings:
    timezone: str
    daily_pipeline_times: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    runtime: RuntimeSettings
    llm: LLMSettings
    product: ProductSettings
    daily_pipeline: DailyPipelineSettings
    scheduler: SchedulerSettings
    agent_mode: str
```

兼容性要求：

- 为了减少一次性改动风险，`Settings` 可以暂时保留 `project_root`、`worker_dir`、`runtime_dir`、`database_url`、`llm_provider`、`llm_model` 等旧属性作为只读兼容属性。
- 新代码优先使用分层配置。
- 旧属性后续可在稳定后再移除。

## 5. 服务层使用方式

### 5.1 DailyPipeline

`DailyPipelineConfig.from_env(settings)` 应调整为 `DailyPipelineConfig.from_settings(settings)`。

目标：

- 不再在 `daily_pipeline_service.py` 中散落读取 `os.getenv`。
- 由 `load_settings()` 统一完成 env 读取、类型转换和默认值处理。
- `DailyPipelineService.run_once()` 仍接收显式 `DailyPipelineConfig`，方便测试覆盖不同参数。

### 5.2 ProductQueryService

`ProductQueryService` 应支持注入 `ProductSettings`。

目标：

- 首页时间窗口、默认 limit、最大 limit 不再散落硬编码。
- `GET /events` 默认行为由后端产品配置决定。
- 测试可以传入自定义 `ProductSettings` 验证窗口策略。

### 5.3 FastAPI

FastAPI app factory 继续保留。

目标：

- `create_app()` 内部通过 dependency 注入 `ProductQueryService`。
- `/events` 的默认 limit 和最大 limit 读取 `ProductSettings`。
- 仍保持只读产品接口，不触发采集、不触发 Agent、不发布。

## 6. 前端设计

前端继续通过 `AI_WORLD_RADAR_API_BASE_URL` 连接 FastAPI。

首页事件数量有两种可接受路径：

- 推荐路径：前端调用 `/events` 时不传 `limit`，由后端默认值控制。
- 兼容路径：前端保留一个轻量 `product-config.ts`，只表达 UI 层分页请求数量，但必须与后端文档一致。

P1 推荐第一种，减少前后端双份配置。

## 7. `.env.example` 调整

`.env.example` 保留环境变量模板，移除不应由本机环境决定的产品策略默认值。

保留：

- 数据库连接
- LLM provider/model/key/base URL
- GitHub token
- Agent mode
- API base URL

移除或降级说明：

- `DAILY_PIPELINE_LOOKBACK_HOURS`
- `DAILY_PIPELINE_SELECTOR_BATCH_SIZE`
- `DAILY_PIPELINE_MAX_SELECTED`
- `DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR`
- `DAILY_PIPELINE_DISABLE_AGENT_FALLBACK`

如果确实需要保留本机 override，必须在注释中明确：这些是本机调试覆盖项，不是产品策略默认值来源。

## 8. 错误处理

配置加载需要显式校验：

- 数字配置必须为正整数，`max_selected` 可为 `None`。
- 时间配置必须为 `HH:MM`。
- `scheduler.timezone` 必须是合法时区字符串。
- 布尔 env override 只接受明确值，例如 `true/false/1/0/yes/no`。
- 无效配置应在启动或脚本执行初期失败，并给出可读错误。

## 9. 测试策略

本轮实施至少覆盖：

- `load_settings()` 默认能组装 `runtime`、`llm`、`product`、`daily_pipeline`、`scheduler`。
- 环境变量可覆盖允许覆盖的配置。
- 无效整数、无效布尔值、无效时间格式会失败。
- `DailyPipelineConfig.from_settings()` 使用 `settings.daily_pipeline`。
- `ProductQueryService.list_published_events()` 默认窗口来自 `ProductSettings`。
- `GET /events` 默认 limit 与最大 limit 来自 `ProductSettings`。
- 前端首页不再硬编码核心产品展示数量，或其 UI 配置与后端文档一致。

## 10. 非目标

本轮不做：

- 数据库配置表。
- 后台配置页面。
- YAML / JSON 配置文件。
- 远程配置中心。
- 定时任务服务实现。
- 首页 UI 重构。
- Agent prompt 或工作流行为调整。

## 11. 验收标准

完成后应满足：

- 配置默认值集中在 typed config 中。
- `.env` 边界清晰，主要保留环境、密钥、连接和运行模式。
- service 层不再直接散落读取 env。
- 首页窗口、首页默认数量、流水线窗口、selector batch、max selected、调度时间都有明确配置归属。
- 相关单测通过。
- 文档说明后续若做后台管理配置，应从 typed config 迁移，而不是继续扩散硬编码。
