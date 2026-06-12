from worker.models import (
    AdminAction,
    AgentRun,
    EventCandidate,
    EventCandidateSignal,
    EventDossier,
    PipelineRun,
    PublishedEvent,
    ReviewResult,
    Source,
    SourceSignal,
)


def test_model_classes_expose_expected_table_names():
    """验证新版模型类暴露预期表名。

    输入：`worker.models` 导出的 10 个 ORM 类。
    输出：断言每个类的 `__tablename__` 等于 P1-1 新表名。
    """
    assert Source.__tablename__ == "sources"
    assert SourceSignal.__tablename__ == "source_signals"
    assert EventCandidate.__tablename__ == "event_candidates"
    assert EventCandidateSignal.__tablename__ == "event_candidate_signals"
    assert EventDossier.__tablename__ == "event_dossiers"
    assert ReviewResult.__tablename__ == "review_results"
    assert PublishedEvent.__tablename__ == "published_events"
    assert PipelineRun.__tablename__ == "pipeline_runs"
    assert AgentRun.__tablename__ == "agent_runs"
    assert AdminAction.__tablename__ == "admin_actions"
