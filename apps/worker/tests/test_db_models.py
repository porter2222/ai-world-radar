from sqlalchemy import create_engine, inspect

from worker.models import Base


P1_CORE_TABLES = {
    "sources",
    "source_signals",
    "event_candidates",
    "event_candidate_signals",
    "event_dossiers",
    "review_results",
    "published_events",
    "pipeline_runs",
    "agent_runs",
    "admin_actions",
}

LEGACY_TABLES = {
    "evidence_cards",
    "event_clusters",
    "event_cluster_cards",
    "content_artifacts",
    "quality_gate_results",
    "briefs",
    "brief_items",
    "raw_items",
}


def test_models_include_new_p1_core_tables():
    """验证 ORM metadata 只服务新版 P1-1 核心表。

    输入：`worker.models.Base.metadata`。
    输出：断言新版 10 张核心表存在，旧主链路表不存在。
    """
    table_names = set(Base.metadata.tables.keys())

    assert P1_CORE_TABLES.issubset(table_names)
    assert LEGACY_TABLES.isdisjoint(table_names)


def test_models_can_create_schema_in_test_database():
    """验证新版 models 能在测试数据库中建表。

    输入：内存 SQLite engine。
    输出：断言新版核心表可以通过 metadata.create_all 创建。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")

    Base.metadata.create_all(engine)

    created_tables = set(inspect(engine).get_table_names())
    assert P1_CORE_TABLES.issubset(created_tables)
