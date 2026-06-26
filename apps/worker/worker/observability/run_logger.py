from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TextIO
from zoneinfo import ZoneInfo


SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "database_url",
    "password",
    "secret",
    "token",
)
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class LogEvent:
    timestamp: str
    level: str
    run_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    component: str
    stage: str
    event: str
    status: str | None
    message_zh: str
    duration_ms: int | None = None
    source_key: str | None = None
    candidate_group_id: str | None = None
    pipeline_run_id: str | None = None
    agent_run_id: str | None = None
    agent_name: str | None = None
    tool_name: str | None = None
    provider: str | None = None
    model: str | None = None
    retry_count: int | None = None
    token_usage: dict[str, int] | None = None
    counts: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Sink(Protocol):
    def emit(self, event: LogEvent) -> None:
        ...


class ConsoleSink:
    def __init__(self, stream: TextIO | None = None):
        self.stream = stream or sys.stdout

    def emit(self, event: LogEvent) -> None:
        self.stream.write(_format_text_event(event) + "\n")
        self.stream.flush()


class TextFileSink:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def emit(self, event: LogEvent) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(_format_text_event(event) + "\n")


class JsonlFileSink:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def emit(self, event: LogEvent) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


class MemorySink:
    def __init__(self):
        self.events: list[LogEvent] = []

    def emit(self, event: LogEvent) -> None:
        self.events.append(event)


class RunLogger:
    def __init__(
        self,
        *,
        run_id: str | None = None,
        trace_id: str | None = None,
        sinks: list[Sink] | None = None,
        now_provider: Any | None = None,
    ):
        self.run_id = run_id or _new_run_id()
        self.trace_id = trace_id or self.run_id
        self.sinks = list(sinks or [])
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.sink_errors: list[dict[str, str]] = []

    def info(self, **kwargs: Any) -> LogEvent:
        return self.emit(level="info", **kwargs)

    def warning(self, **kwargs: Any) -> LogEvent:
        return self.emit(level="warning", **kwargs)

    def error(self, **kwargs: Any) -> LogEvent:
        return self.emit(level="error", **kwargs)

    def emit(
        self,
        *,
        level: str,
        component: str,
        stage: str,
        event: str,
        message_zh: str,
        status: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        duration_ms: int | None = None,
        source_key: str | None = None,
        candidate_group_id: str | None = None,
        pipeline_run_id: str | None = None,
        agent_run_id: str | None = None,
        agent_name: str | None = None,
        tool_name: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        retry_count: int | None = None,
        token_usage: dict[str, int] | None = None,
        counts: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LogEvent:
        sanitized_counts = redact_mapping(counts or {})
        sanitized_metadata = redact_mapping(metadata or {})
        event_obj = LogEvent(
            timestamp=self._timestamp(),
            level=level,
            run_id=self.run_id,
            trace_id=self.trace_id,
            span_id=span_id or _new_span_id(),
            parent_span_id=parent_span_id,
            component=component,
            stage=stage,
            event=event,
            status=status or _default_status(event),
            message_zh=redact_value(message_zh),
            duration_ms=duration_ms,
            source_key=source_key,
            candidate_group_id=candidate_group_id,
            pipeline_run_id=pipeline_run_id,
            agent_run_id=agent_run_id,
            agent_name=agent_name,
            tool_name=tool_name,
            provider=provider,
            model=model,
            retry_count=retry_count,
            token_usage=token_usage,
            counts=sanitized_counts,
            error_type=error_type,
            error_message=redact_value(error_message) if error_message is not None else None,
            metadata=sanitized_metadata,
        )
        for sink in self.sinks:
            try:
                sink.emit(event_obj)
            except Exception as exc:  # noqa: BLE001 - logging failures must not break pipeline
                self.sink_errors.append({"error_type": exc.__class__.__name__, "error_message": str(exc)})
        return event_obj

    @contextmanager
    def stage(
        self,
        *,
        component: str,
        stage: str,
        message_zh: str,
        heartbeat_interval_seconds: float | None = None,
        **kwargs: Any,
    ):
        span_id = _new_span_id()
        started_at = time.perf_counter()
        stop_event = threading.Event()
        heartbeat_thread: threading.Thread | None = None
        self.info(
            component=component,
            stage=stage,
            event="started",
            status="started",
            message_zh=f"{message_zh}开始",
            span_id=span_id,
            **kwargs,
        )

        if heartbeat_interval_seconds is not None and heartbeat_interval_seconds > 0:
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                kwargs={
                    "stop_event": stop_event,
                    "interval_seconds": heartbeat_interval_seconds,
                    "component": component,
                    "stage": stage,
                    "parent_span_id": span_id,
                    "started_at": started_at,
                    "kwargs": kwargs,
                },
                daemon=True,
            )
            heartbeat_thread.start()

        try:
            yield span_id
        except Exception as exc:
            stop_event.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=heartbeat_interval_seconds or 0.1)
            self.error(
                component=component,
                stage=stage,
                event="failed",
                status="failed",
                message_zh=f"{message_zh}失败",
                span_id=_new_span_id(),
                parent_span_id=span_id,
                duration_ms=_elapsed_ms(started_at),
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                **kwargs,
            )
            raise
        else:
            stop_event.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=heartbeat_interval_seconds or 0.1)
            self.info(
                component=component,
                stage=stage,
                event="succeeded",
                status="succeeded",
                message_zh=f"{message_zh}成功",
                span_id=_new_span_id(),
                parent_span_id=span_id,
                duration_ms=_elapsed_ms(started_at),
                **kwargs,
            )

    def _heartbeat_loop(
        self,
        *,
        stop_event: threading.Event,
        interval_seconds: float,
        component: str,
        stage: str,
        parent_span_id: str,
        started_at: float,
        kwargs: dict[str, Any],
    ) -> None:
        while not stop_event.wait(interval_seconds):
            elapsed_seconds = max(0, int(time.perf_counter() - started_at))
            heartbeat_kwargs = dict(kwargs)
            metadata = dict(heartbeat_kwargs.pop("metadata", {}) or {})
            metadata["elapsed_seconds"] = elapsed_seconds
            self.info(
                component=component,
                stage=stage,
                event="heartbeat",
                status="running",
                message_zh=f"仍在运行：{stage}",
                parent_span_id=parent_span_id,
                metadata=metadata,
                **heartbeat_kwargs,
            )

    def _timestamp(self) -> str:
        value = self.now_provider()
        if value.tzinfo is None:
            value = value.replace(tzinfo=LOCAL_TZ)
        return value.astimezone(LOCAL_TZ).isoformat()


class NullRunLogger(RunLogger):
    def __init__(self):
        super().__init__(run_id="noop", sinks=[])


def create_daily_pipeline_logger(
    *,
    runtime_dir: str | Path,
    run_id: str | None = None,
    console: bool = True,
) -> RunLogger:
    runtime_path = Path(runtime_dir)
    runtime_path.mkdir(parents=True, exist_ok=True)
    actual_run_id = run_id or _new_run_id()
    suffix = _file_suffix_from_run_id(actual_run_id)
    timestamp_log = runtime_path / f"daily-pipeline-{suffix}.log"
    timestamp_jsonl = runtime_path / f"daily-pipeline-{suffix}.jsonl"
    latest_log = runtime_path / "daily-pipeline-latest.log"
    latest_jsonl = runtime_path / "daily-pipeline-latest.jsonl"
    sinks: list[Sink] = []
    if console:
        sinks.append(ConsoleSink())
    sinks.extend(
        [
            TextFileSink(latest_log),
            JsonlFileSink(latest_jsonl),
            TextFileSink(timestamp_log),
            JsonlFileSink(timestamp_jsonl),
        ]
    )
    logger = RunLogger(run_id=actual_run_id, sinks=sinks)
    logger.runtime_paths = {
        "latest_log": str(latest_log),
        "latest_jsonl": str(latest_jsonl),
        "timestamp_log": str(timestamp_log),
        "timestamp_jsonl": str(timestamp_jsonl),
    }
    return logger


def redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _redact_by_key(str(key), item) for key, item in value.items()}


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, datetime):
        return _to_local_isoformat(value)
    if not isinstance(value, str):
        return value
    redacted = value
    for secret_value in _known_secret_values():
        if secret_value:
            redacted = redacted.replace(secret_value, "[REDACTED]")
    redacted = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"([?&](?:api_key|apikey|token|access_token|key)=)[^&\s]+", r"\1[REDACTED]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"([A-Za-z][A-Za-z0-9+.\-]*://[^:/@\s]+:)[^@\s]+(@)", r"\1***\2", redacted)
    redacted = re.sub(r"sk-[A-Za-z0-9_\-]+", "[REDACTED]", redacted)
    return _localize_iso_datetime_string(redacted)


def _redact_by_key(key: str, value: Any) -> Any:
    if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    return redact_value(value)


def _known_secret_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if value and len(value) >= 8 and any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
            values.append(value)
    return values


def _to_local_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=LOCAL_TZ)
    return value.astimezone(LOCAL_TZ).isoformat()


def _localize_iso_datetime_string(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})", normalized):
        return value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    return parsed.astimezone(LOCAL_TZ).isoformat()


def _format_text_event(event: LogEvent) -> str:
    time_part = event.timestamp.split("T", maxsplit=1)[-1][:8]
    parts = [
        f"[{time_part}]",
        f"[{event.message_zh}]",
        f"run_id={event.run_id}",
        f"component={event.component}",
        f"stage={event.stage}",
        f"event={event.event}",
    ]
    if event.source_key:
        parts.append(f"source={event.source_key}")
    if event.candidate_group_id:
        parts.append(f"candidate={event.candidate_group_id}")
    if event.agent_name:
        parts.append(f"agent={event.agent_name}")
    if event.tool_name:
        parts.append(f"tool={event.tool_name}")
    if event.provider:
        parts.append(f"provider={event.provider}")
    if event.model:
        parts.append(f"model={event.model}")
    if event.retry_count is not None:
        parts.append(f"retry={event.retry_count}")
    if event.duration_ms is not None:
        parts.append(f"耗时={_format_duration_seconds(event.duration_ms)}")
    if event.counts:
        parts.append("counts=" + json.dumps(event.counts, ensure_ascii=False, sort_keys=True))
    if event.error_type:
        parts.append(f"error={event.error_type}")
    if event.error_message:
        parts.append(f"message={event.error_message}")
    return " ".join(parts)


def _new_run_id() -> str:
    return f"daily_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _new_span_id() -> str:
    return f"span_{uuid.uuid4().hex[:12]}"


def _default_status(event: str) -> str | None:
    if event in {"started", "heartbeat", "succeeded", "failed", "skipped"}:
        return "running" if event == "heartbeat" else event
    return None


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


def _format_duration_seconds(duration_ms: int) -> str:
    return f"{duration_ms / 1000:.2f}秒"


def _file_suffix_from_run_id(run_id: str) -> str:
    match = re.search(r"(\d{8})[_-](\d{6})", run_id)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return datetime.now(LOCAL_TZ).strftime("%Y%m%d-%H%M%S")
