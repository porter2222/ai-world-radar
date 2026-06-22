from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from worker.config import project_root
from worker.db.session import create_worker_engine
from worker.models import AgentRun, Base, PipelineRun, PublishedEvent
from worker.schemas.source import SourceCreate, SourceSignalCreate
from worker.services.signal_service import SignalService
from worker.workflows.event_pipeline import run_event_pipeline


class FakeLLMClient:
    """P1-4 smoke 使用的 fake LLM client。

    输入：预设 response 文本列表。
    输出：记录 chat 调用，并按顺序返回 response。
    """

    provider = "fake"
    model = "fake-model"

    def __init__(self, responses: list[str]):
        """初始化 fake LLM client。

        输入：模型响应文本列表。
        输出：可注入三类 LLM Agent 的 fake client。
        """
        self.responses = responses
        self.calls: list[dict[str, str]] = []

    def chat(self, message: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """模拟 LLMClient.chat。

        输入：user message 和 system_prompt。
        输出：下一条预设模型响应。
        """
        self.calls.append({"message": message, "system_prompt": system_prompt})
        return self.responses.pop(0)


def parse_args() -> argparse.Namespace:
    """解析 P1-4 LLM pipeline smoke 参数。

    输入：命令行参数。
    输出：包含 smoke 模式和可选 database_url 的 argparse Namespace。
    """
    parser = argparse.ArgumentParser(description="Smoke test P1-4 LLM event pipeline.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture-mode", action="store_true", help="使用 fake LLM，不访问真实 provider。")
    mode.add_argument("--call-real-provider", action="store_true", help="使用 .env / 环境变量中的真实 provider 配置。")
    parser.add_argument("--database-url", default=None, help="覆盖 smoke 使用的 SQLite DATABASE_URL。")
    return parser.parse_args()


def main() -> int:
    """运行 P1-4 LLM event pipeline smoke。

    输入：命令行参数、临时数据库和可选真实 provider 配置。
    输出：向 stdout 打印 JSON 摘要，并用进程退出码表达 succeeded/failed。
    """
    args = parse_args()
    database_url = args.database_url or default_smoke_database_url()
    llm_client = FakeLLMClient(fixture_responses()) if args.fixture_mode else None
    mode_label = "fixture" if args.fixture_mode else "real_provider"

    engine = create_worker_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        signal = seed_smoke_signal(session)
        state = run_event_pipeline(
            session,
            signal_ids=[signal.id],
            run_key=f"manual-p1-4-smoke-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            source_scope={"source": "p1-4-smoke", "mode": mode_label},
            agent_mode="llm",
            llm_client=llm_client,
        )
        session.commit()
        summary = build_summary(session, state.run_id, database_url=database_url, mode_label=mode_label)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if summary["status"] == "succeeded" else 1
    except Exception as exc:
        session.rollback()
        summary = {
            "status": "failed",
            "agent_mode": "llm",
            "mode": mode_label,
            "database_url": database_url,
            "error": str(exc),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 1
    finally:
        session.close()
        engine.dispose()


def default_smoke_database_url() -> str:
    """生成默认 smoke SQLite 数据库 URL。

    输入：无。
    输出：位于 runtime/p1-4-smoke 下的 SQLite database_url。
    """
    smoke_dir = project_root() / "runtime" / "p1-4-smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    db_path = smoke_dir / f"llm-event-pipeline-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.sqlite"
    return f"sqlite+pysqlite:///{db_path}"


def seed_smoke_signal(session):
    """写入 P1-4 smoke 使用的来源信号。

    输入：调用方管理事务的 SQLAlchemy Session。
    输出：可传给 workflow 的 SourceSignal ORM 对象。
    """
    service = SignalService(session)
    service.upsert_source(
        SourceCreate(
            source_key="hn_algolia",
            name="Hacker News Algolia",
            source_type="community",
            fetch_method="manual",
            entry_url="https://news.ycombinator.com/",
        )
    )
    return service.upsert_signal(
        SourceSignalCreate(
            source_key="hn_algolia",
            source_item_id="p1-4-heat-hn-1",
            original_title="HN discussion: developers debate OpenAI coding agents",
            original_url="https://news.ycombinator.com/item?id=40617088",
            raw_summary=(
                "HN: 512 points, 186 comments. Developers are discussing whether OpenAI-style "
                "coding agents will change day-to-day software workflows."
            ),
            source_hash=f"hn_algolia:p1-4-heat-hn-{datetime.now(UTC).timestamp()}",
            heat_metrics={"points": 512, "comments": 186, "hn_heat_score": 88},
        )
    )


def build_summary(session, run_id: str | None, *, database_url: str, mode_label: str) -> dict:
    """生成 smoke 输出摘要。

    输入：Session、pipeline run id、数据库 URL 和模式标签。
    输出：用于命令行 stdout 的 JSON dict。
    """
    run = session.get(PipelineRun, run_id) if run_id else None
    agent_runs = session.scalars(select(AgentRun)).all()
    published_events = session.scalars(select(PublishedEvent)).all()
    return {
        "status": run.status if run else "failed",
        "agent_mode": "llm",
        "mode": mode_label,
        "database_url": database_url,
        "run_id": run_id,
        "published_count": len(published_events),
        "agent_runs_count": len(agent_runs),
        "failed_agent_runs_count": len([item for item in agent_runs if item.status == "failed"]),
        "agent_names": [item.agent_name for item in agent_runs],
        "signals_count": run.signals_count if run else 0,
        "candidates_count": run.candidates_count if run else 0,
        "dossiers_count": run.dossiers_count if run else 0,
    }


def fixture_responses() -> list[str]:
    """生成 fake LLM pipeline 响应序列。

    输入：无。
    输出：两份候选事件、一份事件档案和一份审稿结果 JSON。
    """
    return [candidate_json(), candidate_json(), dossier_json(), review_json()]


def candidate_json() -> str:
    """生成 fake LLM 候选事件响应。

    输入：无。
    输出：符合 EventCandidateDraft 的 JSON 字符串。
    """
    return """
{
  "candidate_key": "p1-4-openai-coding-agent",
  "title": "HN 热议 OpenAI 编码 Agent 对开发者工作流的影响",
  "event_type": "community_discussion",
  "category": "模型与产品",
  "primary_subject": "OpenAI",
  "suggested_angle": "从社区讨论热度解释开发者为什么关注编码 Agent。",
  "heat_score": 88,
  "importance_score": 82,
  "audience_value_score": 78,
  "ranking_score": 83,
  "ranking_reason": "HN 高位讨论和评论量说明开发者社区正在集中关注。",
  "merge_reason": "当前 HN 热度信号可单独形成热议型候选事件。"
}
""".strip()


def dossier_json() -> str:
    """生成 fake LLM 事件档案响应。

    输入：无。
    输出：符合 EventDossierDraft 的 JSON 字符串。
    """
    return """
{
  "candidate_key": "p1-4-openai-coding-agent",
  "card_title": "HN 热议 OpenAI 编码 Agent",
  "card_summary": "HN 开发者正在讨论 OpenAI 编码 Agent 对日常工作流的影响。",
  "category": "模型与产品",
  "signal_label": "高热讨论",
  "detail_title": "HN 为什么热议 OpenAI 编码 Agent",
  "detail_summary": "这次热议集中在编码 Agent 对开发者工作流和工具选择的潜在影响。",
  "detail_body": "发生了什么：HN 上开发者正在讨论 OpenAI 编码 Agent 对日常开发工作流的影响。\\n\\n为什么重要：这反映了开发者社区对 AI 编程工具形态变化的关注。\\n\\n后续看什么：观察官方说明、API 能力和社区反馈。",
  "why_it_matters": "这件事有助于中文用户理解 AI 编程工具的新变化。",
  "follow_up_points": ["观察官方文档", "观察社区反馈"],
  "source_refs": [
    {
      "signal_id": "p1-4-heat-hn-1",
      "title": "HN discussion: developers debate OpenAI coding agents",
      "url": "https://news.ycombinator.com/item?id=40617088",
      "source_key": "hn_algolia"
    }
  ],
  "status": "draft"
}
""".strip()


def review_json() -> str:
    """生成 fake LLM 审稿结果响应。

    输入：无。
    输出：符合 ReviewResultDraft 的 JSON 字符串。
    """
    return """
{
  "decision": "publish",
  "risk_level": "low",
  "issues": [],
  "revision_instructions": "",
  "checked_items": {
    "source_supported": true,
    "not_overstated": true,
    "has_chinese_context": true
  }
}
""".strip()


if __name__ == "__main__":
    raise SystemExit(main())
