from __future__ import annotations

import io
import json
import time
from datetime import UTC, datetime

import pytest

from worker.observability.run_logger import (
    ConsoleSink,
    JsonlFileSink,
    MemorySink,
    RunLogger,
    TextFileSink,
    create_daily_pipeline_logger,
)


def test_console_sink_outputs_chinese_message():
    stream = io.StringIO()
    logger = RunLogger(run_id="daily_test", sinks=[ConsoleSink(stream=stream)])

    logger.info(component="daily_pipeline", stage="startup", event="started", message_zh="运行启动")

    output = stream.getvalue()
    assert "[运行启动]" in output
    assert "run_id=daily_test" in output
    assert "component=daily_pipeline" in output


def test_text_log_formats_duration_as_seconds_for_humans():
    stream = io.StringIO()
    logger = RunLogger(run_id="daily_test", sinks=[ConsoleSink(stream=stream)])

    logger.info(
        component="collector",
        stage="collect_sources",
        event="succeeded",
        message_zh="来源采集成功",
        duration_ms=27748,
    )

    output = stream.getvalue()
    assert "耗时=27.75秒" in output
    assert "27748ms" not in output


def test_text_file_and_jsonl_sinks_write_runtime_files(tmp_path):
    text_path = tmp_path / "daily-pipeline-latest.log"
    jsonl_path = tmp_path / "daily-pipeline-latest.jsonl"
    logger = RunLogger(
        run_id="daily_test",
        sinks=[TextFileSink(text_path), JsonlFileSink(jsonl_path)],
    )

    logger.info(
        component="collector",
        stage="collect_source",
        event="succeeded",
        message_zh="采集成功",
        source_key="hn_algolia",
        counts={"written": 3},
    )

    text = text_path.read_text(encoding="utf-8")
    assert "[采集成功]" in text
    assert "source=hn_algolia" in text

    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["message_zh"] == "采集成功"
    assert records[0]["counts"] == {"written": 3}
    assert records[0]["source_key"] == "hn_algolia"


def test_run_logger_redacts_secrets_in_text_json_and_metadata(tmp_path):
    text_path = tmp_path / "redacted.log"
    jsonl_path = tmp_path / "redacted.jsonl"
    logger = RunLogger(
        run_id="daily_test",
        sinks=[TextFileSink(text_path), JsonlFileSink(jsonl_path)],
    )

    logger.error(
        component="llm",
        stage="request",
        event="failed",
        message_zh="LLM请求失败",
        error_message=(
            "Authorization: Bearer sk-secret-123 "
            "postgresql://porter:db-secret@localhost:5432/ai_world_radar"
        ),
        metadata={"OPENAI_API_KEY": "sk-secret-123", "cookie": "session-secret"},
    )

    text = text_path.read_text(encoding="utf-8")
    jsonl_text = jsonl_path.read_text(encoding="utf-8")
    assert "sk-secret-123" not in text
    assert "db-secret" not in text
    assert "session-secret" not in jsonl_text
    assert "[REDACTED]" in jsonl_text


def test_sink_failure_does_not_raise():
    class BrokenSink:
        def emit(self, event):
            raise OSError("disk is read only")

    memory = MemorySink()
    logger = RunLogger(run_id="daily_test", sinks=[BrokenSink(), memory])

    logger.info(component="daily_pipeline", stage="startup", event="started", message_zh="运行启动")

    assert len(memory.events) == 1
    assert logger.sink_errors[0]["error_type"] == "OSError"


def test_stage_records_started_succeeded_and_failed():
    memory = MemorySink()
    logger = RunLogger(run_id="daily_test", sinks=[memory])

    with logger.stage(component="collector", stage="collect_source", message_zh="采集来源"):
        pass

    with pytest.raises(RuntimeError):
        with logger.stage(component="selector", stage="select_candidates", message_zh="筛选候选"):
            raise RuntimeError("selector boom")

    events = [(event.stage, event.event, event.status) for event in memory.events]
    assert ("collect_source", "started", "started") in events
    assert ("collect_source", "succeeded", "succeeded") in events
    assert ("select_candidates", "started", "started") in events
    assert ("select_candidates", "failed", "failed") in events
    assert memory.events[-1].error_type == "RuntimeError"


def test_stage_heartbeat_event_contains_elapsed_seconds():
    memory = MemorySink()
    logger = RunLogger(run_id="daily_test", sinks=[memory])

    with logger.stage(
        component="llm",
        stage="long_request",
        message_zh="LLM长请求",
        heartbeat_interval_seconds=0.01,
    ):
        time.sleep(0.04)

    heartbeats = [event for event in memory.events if event.event == "heartbeat"]
    assert heartbeats
    assert heartbeats[0].metadata["elapsed_seconds"] >= 0
    assert "仍在运行" in heartbeats[0].message_zh


def test_stage_heartbeat_merges_existing_metadata_without_error():
    """验证带 metadata 的阶段心跳不会因为重复 metadata 参数崩溃。

    输入：一次同步心跳循环，kwargs 中已有 metadata。
    输出：心跳事件同时保留原 metadata 和 elapsed_seconds。
    """

    class OneShotStopEvent:
        def __init__(self):
            self.calls = 0

        def wait(self, interval_seconds):
            self.calls += 1
            return self.calls > 1

    memory = MemorySink()
    logger = RunLogger(run_id="daily_test", sinks=[memory])

    logger._heartbeat_loop(
        stop_event=OneShotStopEvent(),
        interval_seconds=0.01,
        component="selector",
        stage="editorial_selector",
        parent_span_id="span_parent",
        started_at=time.perf_counter(),
        kwargs={"metadata": {"batch_size": 30}, "counts": {"candidate_groups": 6}},
    )

    assert len(memory.events) == 1
    assert memory.events[0].event == "heartbeat"
    assert memory.events[0].metadata["batch_size"] == 30
    assert memory.events[0].metadata["elapsed_seconds"] >= 0


def test_create_daily_pipeline_logger_creates_latest_and_timestamp_files(tmp_path):
    logger = create_daily_pipeline_logger(runtime_dir=tmp_path, console=False, run_id="daily_20260626_120000")

    logger.info(component="daily_pipeline", stage="startup", event="started", message_zh="运行启动")

    assert (tmp_path / "daily-pipeline-latest.log").exists()
    assert (tmp_path / "daily-pipeline-latest.jsonl").exists()
    assert (tmp_path / "daily-pipeline-20260626-120000.log").exists()
    assert (tmp_path / "daily-pipeline-20260626-120000.jsonl").exists()


def test_run_logger_timestamps_use_local_shanghai_timezone():
    logger = RunLogger(
        run_id="daily_test",
        sinks=[MemorySink()],
        now_provider=lambda: datetime(2026, 6, 26, 2, 40, 3, tzinfo=UTC),
    )

    event = logger.info(component="daily_pipeline", stage="startup", event="started", message_zh="运行启动")

    assert event.timestamp == "2026-06-26T10:40:03+08:00"


def test_run_logger_converts_nested_metadata_times_to_local_timezone():
    memory = MemorySink()
    logger = RunLogger(run_id="daily_test", sinks=[memory])

    logger.info(
        component="collector",
        stage="collection_window",
        event="started",
        message_zh="collection window",
        metadata={
            "window": {
                "start": "2026-06-25T20:12:35.832419+00:00",
                "end": datetime(2026, 6, 26, 4, 12, 35, tzinfo=UTC),
            }
        },
    )

    metadata = memory.events[0].metadata
    assert metadata["window"]["start"] == "2026-06-26T04:12:35.832419+08:00"
    assert metadata["window"]["end"] == "2026-06-26T12:12:35+08:00"
    assert "+00:00" not in json.dumps(metadata, ensure_ascii=False)
