from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from worker.models import Base
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService


def make_session():
    """创建服务层测试 Session。

    输入：无。
    输出：绑定内存 SQLite 且 `autoflush=False` 的 Session。
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def test_upsert_source_and_signal_are_idempotent():
    """验证来源和信号写入具备幂等性。

    输入：同一个 source_key 与同一个 source_hash 的两次写入。
    输出：SourceSignal 复用同一行，并更新标题和热度指标。
    """
    session = make_session()
    service = SignalService(session)

    source = service.upsert_source(
        SourceCreate(
            source_key="hn_algolia",
            name="Hacker News Algolia",
            source_type="community",
            fetch_method="api",
            entry_url="https://hn.algolia.com/api/v1/search",
        )
    )
    first_signal = service.upsert_signal(
        SourceSignalCreate(
            source_key="hn_algolia",
            source_item_id="123",
            original_title="OpenAI model discussion",
            original_url="https://example.com/openai",
            source_hash="hn_algolia:123",
            heat_metrics={"points": 245},
        )
    )
    second_signal = service.upsert_signal(
        SourceSignalCreate(
            source_key="hn_algolia",
            source_item_id="123",
            original_title="OpenAI model discussion updated",
            original_url="https://example.com/openai",
            source_hash="hn_algolia:123",
            heat_metrics={"points": 300},
        )
    )

    assert source.source_key == "hn_algolia"
    assert first_signal.id == second_signal.id
    assert second_signal.original_title == "OpenAI model discussion updated"
    assert second_signal.heat_metrics["points"] == 300
