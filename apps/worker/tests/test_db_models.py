from sqlalchemy import create_engine, inspect

from worker.db.models import Base


P1_CORE_TABLES = {
    "sources",
    "pipeline_runs",
    "evidence_cards",
    "event_clusters",
    "event_cluster_cards",
    "content_artifacts",
    "quality_gate_results",
    "published_events",
    "briefs",
    "brief_items",
    "admin_actions",
}


def test_models_include_p1_core_tables_only():
    """验证 ORM metadata 覆盖 P1 核心表。

    输入：`Base.metadata`。
    输出：断言 11 张核心表存在，且不创建 raw_items/candidate_events。
    """
    table_names = set(Base.metadata.tables.keys())

    assert P1_CORE_TABLES.issubset(table_names)
    assert "raw_items" not in table_names
    assert "candidate_events" not in table_names


def test_models_can_create_schema_in_test_database():
    """验证 models 能在测试数据库中建表。

    输入：内存 SQLite engine。
    输出：断言核心表可以通过 metadata.create_all 创建。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")

    Base.metadata.create_all(engine)

    created_tables = set(inspect(engine).get_table_names())
    assert P1_CORE_TABLES.issubset(created_tables)
