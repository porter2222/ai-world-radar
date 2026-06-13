from pathlib import Path


WORKER_ROOT = Path(__file__).parents[1]


def test_legacy_runtime_files_are_removed():
    """验证旧版可执行链路文件已被物理删除。

    输入：worker 代码目录。
    输出：断言旧 HN pipeline、旧 Agent stub、旧脚本入口和 legacy 说明文件不再存在。
    """
    removed_paths = [
        WORKER_ROOT / "scripts" / "run_hn_pipeline.py",
        WORKER_ROOT / "worker" / "legacy" / "README.md",
        WORKER_ROOT / "worker" / "pipelines" / "__init__.py",
        WORKER_ROOT / "worker" / "pipelines" / "hn_event_pipeline.py",
        WORKER_ROOT / "worker" / "agents" / "evidence_agent.py",
        WORKER_ROOT / "worker" / "agents" / "event_cluster_agent.py",
        WORKER_ROOT / "worker" / "agents" / "ranking_agent.py",
        WORKER_ROOT / "worker" / "agents" / "detail_writer_agent.py",
        WORKER_ROOT / "worker" / "agents" / "brief_writer_agent.py",
        WORKER_ROOT / "worker" / "agents" / "quality_gate_agent.py",
    ]

    existing_paths = [path for path in removed_paths if path.exists()]

    assert existing_paths == []


def test_worker_runtime_code_does_not_reference_old_event_contracts():
    """验证 worker runtime 不再引用旧事件模型契约名。

    输入：`worker/` 下的 Python 源码。
    输出：断言源码不再出现旧 EvidenceCard/EventCluster/Brief 等契约名。
    """
    forbidden_terms = [
        "EvidenceCard",
        "EventCluster",
        "ContentArtifact",
        "QualityGateResult",
        "BriefItem",
        "Brief",
        "HNEventPipeline",
    ]
    source_files = [
        path
        for path in (WORKER_ROOT / "worker").rglob("*.py")
        if "__pycache__" not in path.parts and "migrations" not in path.parts
    ]

    hits = []
    for path in source_files:
        content = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            if term in content:
                hits.append(f"{path.relative_to(WORKER_ROOT)}: {term}")

    assert hits == []
