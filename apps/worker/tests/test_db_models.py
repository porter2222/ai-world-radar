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
    table_names = set(Base.metadata.tables.keys())

    assert P1_CORE_TABLES.issubset(table_names)
    assert "raw_items" not in table_names
    assert "candidate_events" not in table_names


def test_models_can_create_schema_in_test_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    Base.metadata.create_all(engine)

    created_tables = set(inspect(engine).get_table_names())
    assert P1_CORE_TABLES.issubset(created_tables)
