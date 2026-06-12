from worker.db.migrations import env
from worker.models import Base


def test_alembic_target_metadata_uses_new_base():
    """验证 Alembic target metadata 指向新版模型 Base。

    输入：Alembic env 的 `target_metadata` 和 `worker.models.Base.metadata`。
    输出：断言 metadata 同源，并包含新版表、不包含旧 EvidenceCard 表。
    """
    assert env.target_metadata is Base.metadata
    assert "source_signals" in env.target_metadata.tables
    assert "evidence_cards" not in env.target_metadata.tables
