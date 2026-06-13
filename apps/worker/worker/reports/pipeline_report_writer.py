from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class PipelineReport:
    """新版事件 pipeline 文本报告的数据结构。

    输入：SourceSignal 到 PublishedEvent 的运行统计和错误列表。
    输出：供 `PipelineReportWriter` 渲染为 txt 报告。
    """

    pipeline_run_id: str
    run_key: str
    status: str
    signals_count: int
    candidates_count: int
    dossiers_count: int
    published_count: int
    failed_count: int
    agent_run_count: int
    errors: list[str] = field(default_factory=list)


class PipelineReportWriter:
    """pipeline txt 报告写入器。

    输入：报告输出目录。
    输出：把 `PipelineReport` 渲染并写入 `runtime/pipeline-reports`。
    """

    def __init__(self, report_dir: Path) -> None:
        """初始化报告写入器。

        输入：报告目录 Path。
        输出：无返回值，保存目录供后续写文件使用。
        """
        self.report_dir = report_dir

    def write(self, report: PipelineReport) -> Path:
        """写入 txt 报告。

        输入：`PipelineReport`。
        输出：生成的报告文件路径。
        """
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
        path = self.report_dir / f"{timestamp}-event-pipeline.txt"
        path.write_text(self.render(report), encoding="utf-8")
        return path

    def render(self, report: PipelineReport) -> str:
        """渲染报告文本。

        输入：`PipelineReport`。
        输出：可写入 txt 文件的多行字符串。
        """
        errors = "\n".join(f"- {item}" for item in report.errors) or "- none"
        return "\n".join(
            [
                f"Pipeline Run: {report.pipeline_run_id}",
                f"Run key: {report.run_key}",
                f"Status: {report.status}",
                f"Signals: {report.signals_count}",
                f"Candidates: {report.candidates_count}",
                f"Dossiers: {report.dossiers_count}",
                f"Published events: {report.published_count}",
                f"Failed items: {report.failed_count}",
                f"Agent runs: {report.agent_run_count}",
                "",
                "Errors:",
                errors,
                "",
            ]
        )
