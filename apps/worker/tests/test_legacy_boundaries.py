from pathlib import Path


WORKER_ROOT = Path(__file__).parents[1]
LEGACY_README = WORKER_ROOT / "worker" / "legacy" / "README.md"


def test_legacy_readme_records_new_p1_1_contract():
    """验证遗留说明写明新版 P1-1 主链路。

    输入：`worker/legacy/README.md` 文档。
    输出：断言文档包含新版事件档案链路。
    """
    content = LEGACY_README.read_text(encoding="utf-8")

    assert "SourceSignal -> EventCandidate -> EventDossier -> ReviewResult -> PublishedEvent" in content


def test_legacy_readme_marks_old_contracts_as_reference_only():
    """验证旧 HN 链路只作为参考资料保留。

    输入：`worker/legacy/README.md` 文档。
    输出：断言旧对象名和旧入口被标记为非 P1-1 实现契约。
    """
    content = LEGACY_README.read_text(encoding="utf-8")

    for old_name in [
        "EvidenceCard",
        "EventCluster",
        "ContentArtifact",
        "QualityGateResult",
        "Brief",
        "BriefItem",
    ]:
        assert old_name in content

    assert "worker/pipelines/hn_event_pipeline.py" in content
    assert "scripts/run_hn_pipeline.py" in content
    assert "not P1-1 entrypoints" in content
