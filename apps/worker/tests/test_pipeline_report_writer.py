from pathlib import Path

from worker.reports.pipeline_report_writer import PipelineReport, PipelineReportWriter


def test_pipeline_report_writer_generates_txt_report(tmp_path):
    """验证 pipeline 报告写入 txt。

    输入：fake PipelineReport 和临时目录。
    输出：断言生成 txt 文件且包含关键统计和失败信息。
    """
    report = PipelineReport(
        pipeline_run_id="run-1",
        status="success",
        days=7,
        limit=100,
        fetched_count=3,
        evidence_card_count=3,
        event_cluster_count=3,
        published_event_count=2,
        brief_item_count=2,
        quality_gate_failures=["cluster-3 missing detail"],
        errors=[],
    )

    path = PipelineReportWriter(tmp_path).write(report)

    text = path.read_text(encoding="utf-8")
    assert path.suffix == ".txt"
    assert "Pipeline Run: run-1" in text
    assert "Published events: 2" in text
    assert "cluster-3 missing detail" in text
