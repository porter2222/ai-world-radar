from pathlib import Path

from worker.reports.pipeline_report_writer import PipelineReport, PipelineReportWriter


def test_pipeline_report_writer_generates_txt_report(tmp_path):
    """验证新版事件 pipeline 报告写入 txt。

    输入：新版 fake PipelineReport 和临时目录。
    输出：断言生成 txt 文件且只包含 SourceSignal 到 PublishedEvent 统计。
    """
    report = PipelineReport(
        pipeline_run_id="run-1",
        run_key="manual-p1-2-report",
        status="succeeded",
        signals_count=3,
        candidates_count=2,
        dossiers_count=2,
        published_count=1,
        failed_count=0,
        agent_run_count=3,
        errors=[],
    )

    path = PipelineReportWriter(tmp_path).write(report)

    text = path.read_text(encoding="utf-8")
    assert path.suffix == ".txt"
    assert "Pipeline Run: run-1" in text
    assert "Run key: manual-p1-2-report" in text
    assert "Signals: 3" in text
    assert "Published events: 1" in text
    assert "Evidence cards" not in text
    assert "Brief items" not in text
