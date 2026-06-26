# Config System Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize AI World Radar runtime, product, daily pipeline, and scheduler configuration behind typed settings while keeping `.env` focused on environment, secrets, connections, and runtime mode.

**Architecture:** Extend `apps/worker/worker/config.py` into the single backend configuration entrypoint with nested dataclasses and validation. Refactor daily pipeline and product query/API code to consume those settings instead of hardcoded defaults or service-local env reads. Let the frontend rely on backend `/events` defaults rather than defining the core homepage item count itself.

**Tech Stack:** Python dataclasses, python-dotenv, FastAPI Query dependencies, SQLAlchemy service tests, pytest, Next.js, Vitest, TypeScript.

---

## File Structure

- Modify: `apps/worker/worker/config.py`
  - Owns typed settings, env parsing, default values, compatibility properties, and validation helpers.
- Modify: `apps/worker/worker/services/daily_pipeline_service.py`
  - Converts `DailyPipelineConfig.from_env()` to `from_settings()` and removes service-local `os.getenv`.
- Modify: `apps/worker/worker/services/product_query_service.py`
  - Accepts `ProductSettings` and uses it for homepage recency/backfill/default pagination behavior.
- Modify: `apps/worker/worker/api/dependencies.py`
  - Injects `ProductQueryService` with `settings.product`.
- Modify: `apps/worker/worker/api/app.py`
  - Uses `ProductSettings` for `/events` default and max limit.
- Modify: `apps/worker/scripts/run_daily_pipeline.py`
  - Calls `DailyPipelineConfig.from_settings(settings)`.
- Modify: `apps/web/lib/product-api.ts`
  - Stops forcing default `limit=20` when caller does not pass a limit.
- Modify: `apps/web/app/page.tsx`
  - Calls `getEvents()` without hardcoded `limit`.
- Modify: `.env.example`
  - Keeps environment and secret keys; removes daily pipeline product/strategy defaults as normal env template values.
- Modify: `apps/worker/tests/test_config.py`
  - Covers nested settings, defaults, env overrides, and validation failures.
- Modify: `apps/worker/tests/test_daily_pipeline_service.py`
  - Covers `DailyPipelineConfig.from_settings()`.
- Modify: `apps/worker/tests/test_product_query_service.py`
  - Covers product settings driven homepage window.
- Modify: `apps/worker/tests/test_product_api.py`
  - Covers `/events` default/max limit from product settings.
- Modify: `apps/web/lib/product-api.test.ts`
  - Covers no forced limit when omitted and explicit limit when provided.
- Modify: `docs/07-验收与运行/后端P1测试记录.md`
  - Records tests, real pipeline run, FastAPI smoke, and frontend verification.

---

### Task 1: Config Typed Settings and Validation

**Files:**
- Modify: `apps/worker/tests/test_config.py`
- Modify: `apps/worker/worker/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing config tests**

Add these tests to `apps/worker/tests/test_config.py`:

```python
import pytest

from worker.config import load_settings


def test_load_settings_exposes_typed_config_groups(monkeypatch, tmp_path):
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    for key in [
        "DATABASE_URL",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "AGENT_MODE",
        "DAILY_PIPELINE_LOOKBACK_HOURS",
        "DAILY_PIPELINE_MAX_SELECTED",
        "SCHEDULER_DAILY_PIPELINE_TIMES",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()

    assert settings.runtime.project_root == tmp_path
    assert settings.runtime.worker_dir == tmp_path / "apps" / "worker"
    assert settings.runtime.runtime_dir == tmp_path / "runtime"
    assert settings.runtime.database_url.startswith("postgresql+psycopg://")
    assert settings.llm.provider == "openai"
    assert settings.llm.model == "gpt-4o-mini"
    assert settings.llm.request_timeout_seconds == 180
    assert settings.agent_mode == "llm"
    assert settings.product.homepage_recent_hours == 12
    assert settings.product.homepage_default_limit == 20
    assert settings.product.homepage_max_limit == 100
    assert settings.product.homepage_min_recent_items == 8
    assert settings.product.homepage_backfill_days is None
    assert settings.daily_pipeline.source_group == "daily_all"
    assert settings.daily_pipeline.lookback_hours == 8
    assert settings.daily_pipeline.candidate_lookback_hours == 48
    assert settings.daily_pipeline.selector_batch_size == 30
    assert settings.daily_pipeline.max_selected == 5
    assert settings.daily_pipeline.continue_on_source_error is True
    assert settings.daily_pipeline.disable_agent_fallback is True
    assert settings.scheduler.timezone == "Asia/Shanghai"
    assert settings.scheduler.daily_pipeline_times == ("08:00", "13:00", "20:00")


def test_load_settings_keeps_legacy_compatibility_properties(monkeypatch, tmp_path):
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    settings = load_settings()

    assert settings.project_root == settings.runtime.project_root
    assert settings.worker_dir == settings.runtime.worker_dir
    assert settings.runtime_dir == settings.runtime.runtime_dir
    assert settings.database_url == settings.runtime.database_url
    assert settings.llm_provider == "deepseek"
    assert settings.llm_model == "deepseek-chat"


def test_load_settings_allows_explicit_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    monkeypatch.setenv("DAILY_PIPELINE_LOOKBACK_HOURS", "6")
    monkeypatch.setenv("DAILY_PIPELINE_MAX_SELECTED", "0")
    monkeypatch.setenv("DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR", "false")
    monkeypatch.setenv("DAILY_PIPELINE_DISABLE_AGENT_FALLBACK", "yes")
    monkeypatch.setenv("SCHEDULER_DAILY_PIPELINE_TIMES", "09:15,18:45")

    settings = load_settings()

    assert settings.daily_pipeline.lookback_hours == 6
    assert settings.daily_pipeline.max_selected is None
    assert settings.daily_pipeline.continue_on_source_error is False
    assert settings.daily_pipeline.disable_agent_fallback is True
    assert settings.scheduler.daily_pipeline_times == ("09:15", "18:45")


@pytest.mark.parametrize("key,value", [
    ("DAILY_PIPELINE_LOOKBACK_HOURS", "0"),
    ("DAILY_PIPELINE_SELECTOR_BATCH_SIZE", "-1"),
    ("LLM_REQUEST_TIMEOUT_SECONDS", "abc"),
])
def test_load_settings_rejects_invalid_positive_int(monkeypatch, tmp_path, key, value):
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    monkeypatch.setenv(key, value)

    with pytest.raises(ValueError, match=key):
        load_settings()


def test_load_settings_rejects_invalid_bool(monkeypatch, tmp_path):
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    monkeypatch.setenv("DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR", "maybe")

    with pytest.raises(ValueError, match="DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR"):
        load_settings()


def test_load_settings_rejects_invalid_schedule_time(monkeypatch, tmp_path):
    monkeypatch.setattr("worker.config.project_root", lambda: tmp_path)
    monkeypatch.setenv("SCHEDULER_DAILY_PIPELINE_TIMES", "08:00,25:00")

    with pytest.raises(ValueError, match="SCHEDULER_DAILY_PIPELINE_TIMES"):
        load_settings()
```

Update `test_env_example_contains_local_runtime_closure_keys()` so `required_keys` removes daily pipeline strategy keys and asserts those keys are not normal template assignments:

```python
for removed_key in {
    "DAILY_PIPELINE_LOOKBACK_HOURS",
    "DAILY_PIPELINE_SELECTOR_BATCH_SIZE",
    "DAILY_PIPELINE_MAX_SELECTED",
    "DAILY_PIPELINE_CONTINUE_ON_SOURCE_ERROR",
    "DAILY_PIPELINE_DISABLE_AGENT_FALLBACK",
}:
    assert removed_key not in present_keys
```

- [ ] **Step 2: Run RED config tests**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -v
```

Expected: FAIL because `settings.runtime`, `settings.product`, `settings.daily_pipeline`, `settings.scheduler`, and validation helpers do not exist yet.

- [ ] **Step 3: Implement typed settings in `config.py`**

Replace `apps/worker/worker/config.py` with the expanded dataclass structure. Keep the existing `project_root()` and `_default_llm_model()` behavior.

Implementation must include:

```python
@dataclass(frozen=True)
class RuntimeSettings:
    project_root: Path
    worker_dir: Path
    runtime_dir: Path
    database_url: str
```

```python
@dataclass(frozen=True)
class Settings:
    runtime: RuntimeSettings
    llm: LLMSettings
    product: ProductSettings
    daily_pipeline: DailyPipelineSettings
    scheduler: SchedulerSettings
    agent_mode: str

    @property
    def project_root(self) -> Path:
        return self.runtime.project_root

    @property
    def llm_provider(self) -> str:
        return self.llm.provider
```

Implement helpers:

```python
def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value
```

```python
def _env_optional_positive_int(name: str, default: int | None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = int(raw)
    if value == 0:
        return None
    if value < 0:
        raise ValueError(f"{name} must be a positive integer or 0")
    return value
```

```python
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
```

```python
def _env_schedule_times(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    values = default if raw is None or raw.strip() == "" else tuple(part.strip() for part in raw.split(",") if part.strip())
    for value in values:
        hour, minute = value.split(":", maxsplit=1)
        if len(hour) != 2 or len(minute) != 2 or not hour.isdigit() or not minute.isdigit():
            raise ValueError(f"{name} values must use HH:MM")
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError(f"{name} values must use valid HH:MM times")
    return values
```

Use defaults from the spec:

```python
ProductSettings(
    homepage_recent_hours=_env_positive_int("PRODUCT_HOMEPAGE_RECENT_HOURS", 12),
    homepage_default_limit=_env_positive_int("PRODUCT_HOMEPAGE_DEFAULT_LIMIT", 20),
    homepage_max_limit=_env_positive_int("PRODUCT_HOMEPAGE_MAX_LIMIT", 100),
    homepage_min_recent_items=_env_positive_int("PRODUCT_HOMEPAGE_MIN_RECENT_ITEMS", 8),
    homepage_backfill_days=_env_optional_positive_int("PRODUCT_HOMEPAGE_BACKFILL_DAYS", None),
)
```

Do not add these product keys to `.env.example` as required runtime keys.

- [ ] **Step 4: Clean `.env.example`**

Remove normal assignments for daily pipeline strategy keys from `.env.example`. Leave a short note:

```text
# Product and pipeline strategy defaults live in typed config.
# Use explicit process env overrides only for local diagnostics.
```

- [ ] **Step 5: Run GREEN config tests**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add apps/worker/worker/config.py apps/worker/tests/test_config.py .env.example
git commit -m "feat(worker): add typed configuration settings"
```

---

### Task 2: Daily Pipeline Uses Unified Settings

**Files:**
- Modify: `apps/worker/tests/test_daily_pipeline_service.py`
- Modify: `apps/worker/worker/services/daily_pipeline_service.py`
- Modify: `apps/worker/scripts/run_daily_pipeline.py`

- [ ] **Step 1: Write failing daily pipeline config test**

Add to `apps/worker/tests/test_daily_pipeline_service.py`:

```python
from worker.config import DailyPipelineSettings, LLMSettings, ProductSettings, RuntimeSettings, SchedulerSettings, Settings
from pathlib import Path


def test_daily_pipeline_config_builds_from_settings():
    settings = Settings(
        runtime=RuntimeSettings(
            project_root=Path("D:/tmp/project"),
            worker_dir=Path("D:/tmp/project/apps/worker"),
            runtime_dir=Path("D:/tmp/project/runtime"),
            database_url="sqlite+pysqlite:///:memory:",
        ),
        llm=LLMSettings(provider="openai", model="gpt-4o-mini", request_timeout_seconds=180),
        product=ProductSettings(
            homepage_recent_hours=12,
            homepage_default_limit=20,
            homepage_max_limit=100,
            homepage_min_recent_items=8,
            homepage_backfill_days=None,
        ),
        daily_pipeline=DailyPipelineSettings(
            source_group="daily_test",
            lookback_hours=6,
            candidate_lookback_hours=24,
            selector_batch_size=12,
            max_selected=None,
            continue_on_source_error=False,
            disable_agent_fallback=True,
        ),
        scheduler=SchedulerSettings(timezone="Asia/Shanghai", daily_pipeline_times=("08:00",)),
        agent_mode="llm",
    )

    config = DailyPipelineConfig.from_settings(settings)

    assert config.source_group == "daily_test"
    assert config.lookback_hours == 6
    assert config.candidate_lookback_hours == 24
    assert config.selector_batch_size == 12
    assert config.max_selected is None
    assert config.continue_on_source_error is False
    assert config.disable_agent_fallback is True
    assert config.agent_mode == "llm"
```

- [ ] **Step 2: Run RED daily pipeline test**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_daily_pipeline_service.py::test_daily_pipeline_config_builds_from_settings -v
```

Expected: FAIL because `DailyPipelineConfig.from_settings()` does not exist.

- [ ] **Step 3: Implement `DailyPipelineConfig.from_settings()`**

In `apps/worker/worker/services/daily_pipeline_service.py`, replace `from_env()` with:

```python
@classmethod
def from_settings(cls, settings: Settings) -> "DailyPipelineConfig":
    daily = settings.daily_pipeline
    return cls(
        source_group=daily.source_group,
        lookback_hours=daily.lookback_hours,
        selector_batch_size=daily.selector_batch_size,
        continue_on_source_error=daily.continue_on_source_error,
        disable_agent_fallback=daily.disable_agent_fallback,
        max_selected=daily.max_selected,
        agent_mode=settings.agent_mode,
        candidate_lookback_hours=daily.candidate_lookback_hours,
    )
```

Remove `_env_bool()` from this file if unused after the refactor.

- [ ] **Step 4: Update CLI entry**

In `apps/worker/scripts/run_daily_pipeline.py`, change:

```python
config = DailyPipelineConfig.from_env(settings)
```

to:

```python
config = DailyPipelineConfig.from_settings(settings)
```

- [ ] **Step 5: Run daily pipeline targeted tests**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_daily_pipeline_service.py tests/test_run_daily_pipeline_script.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add apps/worker/worker/services/daily_pipeline_service.py apps/worker/scripts/run_daily_pipeline.py apps/worker/tests/test_daily_pipeline_service.py
git commit -m "refactor(worker): load daily pipeline config from settings"
```

---

### Task 3: Product Settings Drive Query Service and FastAPI

**Files:**
- Modify: `apps/worker/tests/test_product_query_service.py`
- Modify: `apps/worker/tests/test_product_api.py`
- Modify: `apps/worker/worker/services/product_query_service.py`
- Modify: `apps/worker/worker/api/dependencies.py`
- Modify: `apps/worker/worker/api/app.py`

- [ ] **Step 1: Write failing product query settings test**

In `apps/worker/tests/test_product_query_service.py`, import `ProductSettings` and add:

```python
from worker.config import ProductSettings


def test_list_published_events_uses_injected_product_settings_window():
    session = make_session()
    now = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    recent = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(session, candidate_key="settings-recent-event", title="配置近期事件"),
    )
    recent.published_at = now - timedelta(hours=3)
    old = publish_reviewed_dossier(
        session,
        create_reviewed_dossier(session, candidate_key="settings-old-event", title="配置过期事件"),
    )
    old.published_at = now - timedelta(hours=13)
    session.commit()

    service = ProductQueryService(
        session,
        product_settings=ProductSettings(
            homepage_recent_hours=12,
            homepage_default_limit=20,
            homepage_max_limit=100,
            homepage_min_recent_items=1,
            homepage_backfill_days=None,
        ),
    )
    slugs = [item.slug for item in service.list_published_events(limit=20, offset=0, now=now)]

    assert recent.slug in slugs
    assert old.slug not in slugs
```

- [ ] **Step 2: Write failing API settings test**

In `apps/worker/tests/test_product_api.py`, import `ProductSettings` and add:

```python
from worker.config import ProductSettings


def test_events_api_uses_product_settings_default_and_max_limit():
    session_factory = make_session_factory()
    with session_factory() as session:
        create_published_event(session, "api-config-limit")
        session.commit()

    client = TestClient(
        create_app(
            session_factory=session_factory,
            product_settings=ProductSettings(
                homepage_recent_hours=48,
                homepage_default_limit=7,
                homepage_max_limit=9,
                homepage_min_recent_items=1,
                homepage_backfill_days=None,
            ),
        )
    )

    default_response = client.get("/events")
    assert default_response.status_code == 200
    assert default_response.json()["limit"] == 7

    too_large_response = client.get("/events?limit=10")
    assert too_large_response.status_code == 422
```

- [ ] **Step 3: Run RED product tests**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py::test_list_published_events_uses_injected_product_settings_window tests/test_product_api.py::test_events_api_uses_product_settings_default_and_max_limit -v
```

Expected: FAIL because `ProductQueryService` and `create_app()` do not accept `product_settings`.

- [ ] **Step 4: Implement ProductQueryService settings injection**

In `apps/worker/worker/services/product_query_service.py`:

```python
from worker.config import ProductSettings, load_settings
```

Change constructor:

```python
def __init__(self, session: Session, *, product_settings: ProductSettings | None = None):
    self.session = session
    self.product_settings = product_settings or load_settings().product
```

Change `list_published_events()` defaults to optional:

```python
limit: int | None = None,
recent_hours: int | None = None,
min_recent_items: int | None = None,
backfill_days: int | None = None,
```

At method start:

```python
settings = self.product_settings
effective_limit = limit if limit is not None else settings.homepage_default_limit
effective_recent_hours = recent_hours if recent_hours is not None else settings.homepage_recent_hours
effective_min_recent_items = min_recent_items if min_recent_items is not None else settings.homepage_min_recent_items
effective_backfill_days = backfill_days if backfill_days is not None else settings.homepage_backfill_days
```

If `effective_backfill_days is None`, use `recent_cutoff` directly and skip the recent-count backfill query.

Paginate with:

```python
paginated_events = events[offset : offset + effective_limit]
```

- [ ] **Step 5: Implement FastAPI product settings injection**

In `apps/worker/worker/api/dependencies.py`:

```python
from worker.config import ProductSettings

def create_product_query_dependency(
    session_factory: SessionFactory,
    *,
    product_settings: ProductSettings | None = None,
) -> Callable[[], Iterator[ProductQueryService]]:
    ...
    yield ProductQueryService(session, product_settings=product_settings)
```

In `apps/worker/worker/api/app.py`:

```python
from worker.config import ProductSettings, load_settings
```

Change signature:

```python
def create_app(session_factory: SessionFactory | None = None, product_settings: ProductSettings | None = None) -> FastAPI:
```

Resolve:

```python
resolved_product_settings = product_settings or load_settings().product
query_dependency = create_product_query_dependency(
    resolved_session_factory,
    product_settings=resolved_product_settings,
)
```

For `/events`, avoid static max in `Query` because max is runtime config. Use:

```python
limit: int | None = Query(None, ge=1),
```

Then validate:

```python
effective_limit = limit or resolved_product_settings.homepage_default_limit
if effective_limit > resolved_product_settings.homepage_max_limit:
    raise HTTPException(status_code=422, detail=f"limit must be <= {resolved_product_settings.homepage_max_limit}")
```

Return `"limit": effective_limit`.

- [ ] **Step 6: Run product targeted tests**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_product_query_service.py tests/test_product_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add apps/worker/worker/services/product_query_service.py apps/worker/worker/api/dependencies.py apps/worker/worker/api/app.py apps/worker/tests/test_product_query_service.py apps/worker/tests/test_product_api.py
git commit -m "refactor(worker): drive product queries from settings"
```

---

### Task 4: Frontend Stops Owning Backend Homepage Defaults

**Files:**
- Modify: `apps/web/lib/product-api.test.ts`
- Modify: `apps/web/lib/product-api.ts`
- Modify: `apps/web/app/page.tsx`

- [ ] **Step 1: Write failing frontend API client tests**

In `apps/web/lib/product-api.test.ts`, change the first test call to:

```ts
const result = await getEvents();

expect(fetchMock).toHaveBeenCalledWith("http://api.test/events?offset=0", { cache: "no-store" });
```

Add explicit limit test:

```ts
it("passes an explicit event limit only when the caller asks for one", async () => {
  vi.stubEnv("AI_WORLD_RADAR_API_BASE_URL", "http://api.test");
  const fetchMock = vi.fn(async () => jsonResponse({ items: [], limit: 12, offset: 0 }));
  vi.stubGlobal("fetch", fetchMock);

  await getEvents({ limit: 12, offset: 0 });

  expect(fetchMock).toHaveBeenCalledWith("http://api.test/events?limit=12&offset=0", { cache: "no-store" });
});
```

- [ ] **Step 2: Run RED frontend API client tests**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\web"
npm test -- product-api.test.ts
```

Expected: FAIL because `getEvents()` still sends `limit=20`.

- [ ] **Step 3: Implement frontend request change**

In `apps/web/lib/product-api.ts`, change `getEvents`:

```ts
const params = new URLSearchParams();
if (query.limit !== undefined) {
  params.set("limit", String(query.limit));
}
params.set("offset", String(query.offset ?? 0));
if (query.category) {
  params.set("category", query.category);
}
const queryString = params.toString();
return fetchJson<ProductEventListResponse>(queryString ? `/events?${queryString}` : "/events");
```

In `apps/web/app/page.tsx`, change:

```ts
const events = await getEvents({ limit: 20, offset: 0 });
```

to:

```ts
const events = await getEvents();
```

- [ ] **Step 4: Run frontend tests**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\web"
npm test -- product-api.test.ts
npm test
npm run typecheck
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
git add apps/web/lib/product-api.ts apps/web/lib/product-api.test.ts apps/web/app/page.tsx
git commit -m "refactor(web): rely on backend event defaults"
```

---

### Task 5: Regression, Real Runtime Validation, and Documentation

**Files:**
- Modify: `docs/07-验收与运行/后端P1测试记录.md`

- [ ] **Step 1: Run worker targeted regression**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_daily_pipeline_service.py tests/test_product_query_service.py tests/test_product_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend regression**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\web"
npm test
npm run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run real daily pipeline**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe scripts\run_daily_pipeline.py
```

Expected:

- Console prints Chinese stage logs.
- Final JSON summary has `status` in `succeeded`, `no_new_signals`, `no_candidate_groups`, or `no_selected_candidates`.
- Output does not include `DATABASE_URL`, API key values, or database password.
- `D:\AI World Radar-worktrees\config-system\runtime\daily-pipeline-latest.log` exists.
- `D:\AI World Radar-worktrees\config-system\runtime\daily-pipeline-latest.jsonl` exists.

- [ ] **Step 4: Start FastAPI and run real HTTP smoke**

Start in one PowerShell:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\worker"
.\.venv\Scripts\python.exe -m uvicorn worker.api.app:create_app --factory --host 127.0.0.1 --port 8016
```

In another PowerShell:

```powershell
Invoke-RestMethod "http://127.0.0.1:8016/health"
$events = Invoke-RestMethod "http://127.0.0.1:8016/events"
$events.items.Count
if ($events.items.Count -gt 0) {
  $slug = $events.items[0].slug
  Invoke-RestMethod "http://127.0.0.1:8016/events/$slug"
}
```

Expected:

- `/health` returns `{"status":"ok"}`.
- `/events` returns JSON with `items`, `limit`, and `offset`.
- If at least one event exists, `/events/{slug}` returns detail JSON.

Stop FastAPI with `Ctrl+C` after smoke.

- [ ] **Step 5: Optional Next.js smoke if frontend code changed**

Because Task 4 changes frontend request logic, run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system\apps\web"
npm run dev
```

Open `http://127.0.0.1:3000` or use a local browser smoke. Expected: homepage renders event cards or empty state without request errors.

Stop Next.js with `Ctrl+C`.

- [ ] **Step 6: Record acceptance evidence**

Append a section to `docs/07-验收与运行/后端P1测试记录.md`:

```markdown
## 2026-06-26 配置体系规范化验收记录

- 工作区：`D:\AI World Radar-worktrees\config-system`
- 分支：`codex/config-system`
- 目标：统一 typed config，规范 `.env` 边界，移除 service 层散落 env 读取和前端硬编码首页默认数量。

| 验证项 | 命令 | 结果记录方式 |
|---|---|---|
| worker targeted regression | `.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_daily_pipeline_service.py tests/test_product_query_service.py tests/test_product_api.py -v` | 记录 pytest 汇总行，例如 `N passed in Xs` |
| frontend tests | `npm test` | 记录 Vitest 汇总行，例如 `Test Files ... Tests ...` |
| frontend typecheck | `npm run typecheck` | 记录命令退出结果；成功时写 `通过，无 TypeScript 错误` |
| real daily pipeline | `.\.venv\Scripts\python.exe scripts\run_daily_pipeline.py` | 记录 final summary 的 `status`、关键计数和 runtime 日志路径 |
| FastAPI smoke | `/health`, `/events`, `/events/{slug}` | 记录 HTTP 状态码、事件数量和详情 slug |
| Next.js smoke | `npm run dev` | 记录本地页面 URL、页面渲染结果，或记录未执行的具体原因 |

结论必须说明：配置体系规范化是否通过验收；如有风险，列出风险和不阻塞发布的原因。
```

Use actual command results from the local run. Do not include secrets.

- [ ] **Step 7: Final checks**

Run:

```powershell
Set-Location "D:\AI World Radar-worktrees\config-system"
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files modified before commit.

- [ ] **Step 8: Commit Task 5**

```powershell
git add docs/07-验收与运行/后端P1测试记录.md
git commit -m "docs: record config system acceptance"
```

---

## Final Completion Audit

- [ ] Confirm `.env` exists locally in `D:\AI World Radar-worktrees\config-system\.env` and is not tracked by Git.
- [ ] Confirm no committed file contains API keys, database passwords, or runtime logs.
- [ ] Confirm `git status --short --branch` is clean.
- [ ] Confirm all required tests and real runtime checks above passed or have an explicit non-secret failure explanation that was fixed.
- [ ] Confirm final response lists modified files, test commands/results, real validation evidence, and residual risks.
