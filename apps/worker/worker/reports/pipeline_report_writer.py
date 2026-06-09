from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class PipelineReport:
    """pipeline 文本报告的数据结构。

    输入：pipeline 运行统计、质量门禁失败和错误列表。
    输出：供 `PipelineReportWriter` 渲染为 txt 报告。
    """

    pipeline_run_id: str
    status: str
    days: int
    limit: int
    fetched_count: int
    evidence_card_count: int
    event_cluster_count: int
    published_event_count: int
    brief_item_count: int
    quality_gate_failures: list[str] = field(default_factory=list)
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
        path = self.report_dir / f"{timestamp}-hn-event-pipeline.txt"
        path.write_text(self.render(report), encoding="utf-8")
        return path

    def render(self, report: PipelineReport) -> str:
        """渲染报告文本。

        输入：`PipelineReport`。
        输出：可写入 txt 文件的多行字符串。
        """
        quality_gate_failures = "\n".join(f"- {item}" for item in report.quality_gate_failures) or "- none"
        errors = "\n".join(f"- {item}" for item in report.errors) or "- none"
        return "\n".join(
            [
                f"Pipeline Run: {report.pipeline_run_id}",
                f"Status: {report.status}",
                f"Parameters: days={report.days}, limit={report.limit}",
                f"Fetched stories: {report.fetched_count}",
                f"Evidence cards: {report.evidence_card_count}",
                f"Event clusters: {report.event_cluster_count}",
                f"Published events: {report.published_event_count}",
                f"Brief items: {report.brief_item_count}",
                "",
                "Quality gate failures:",
                quality_gate_failures,
                "",
                "Errors:",
                errors,
                "",
            ]
        )
