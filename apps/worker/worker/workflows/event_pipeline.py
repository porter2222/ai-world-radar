from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from worker.agents.factory import create_event_agents
from worker.models import EventCandidate, EventDossier
from worker.schemas.workflow import EventPipelineState
from worker.tools.event_pipeline_tools import EventPipelineTools


def run_event_pipeline(
    session: Session,
    *,
    signal_ids: list[str],
    run_key: str,
    source_scope: dict[str, Any] | None = None,
    agent_mode: str = "stub",
    llm_client: Any | None = None,
    tools: EventPipelineTools | None = None,
) -> EventPipelineState:
    """运行 P1-2 事件档案生产工作流。

    输入：数据库 Session、待处理 SourceSignal ID、run_key、来源范围、Agent 模式和可选注入 tools。
    输出：最终 EventPipelineState，包含 run、candidate、dossier、review 和发布结果。
    """
    pipeline_tools = tools or EventPipelineTools(
        session,
        agents=create_event_agents(mode=agent_mode, llm_client=llm_client),
    )
    graph = _build_event_pipeline_graph(pipeline_tools)
    initial_state = EventPipelineState(
        run_key=run_key,
        signal_ids=signal_ids,
        source_scope=source_scope or {},
        status="initialized",
    )
    final_state = graph.invoke(initial_state.model_dump())
    return EventPipelineState.model_validate(final_state)


def _build_event_pipeline_graph(tools: EventPipelineTools):
    """构建 LangGraph 事件工作流。

    输入：绑定当前 Session 的 EventPipelineTools。
    输出：已 compile 的 LangGraph workflow，可接收 dict 状态并返回 dict 状态。
    """
    graph = StateGraph(dict)
    graph.add_node("collect_signals", _collect_signals_node(tools))
    graph.add_node("normalize_signals", _normalize_signals_node(tools))
    graph.add_node("editorial_triage", _editorial_triage_node(tools))
    graph.add_node("merge_and_rank_events", _merge_and_rank_events_node(tools))
    graph.add_node("build_research_package", _build_research_package_node())
    graph.add_node("draft_event_dossier", _draft_event_dossier_node(tools))
    graph.add_node("review_event_dossier", _review_event_dossier_node(tools))
    graph.add_node("revise_if_needed", _revise_if_needed_node())
    graph.add_node("publish_or_manual_review", _publish_or_manual_review_node(tools))
    graph.add_node("record_run", _record_run_node(tools))

    graph.set_entry_point("collect_signals")
    graph.add_edge("collect_signals", "normalize_signals")
    graph.add_edge("normalize_signals", "editorial_triage")
    graph.add_edge("editorial_triage", "merge_and_rank_events")
    graph.add_edge("merge_and_rank_events", "build_research_package")
    graph.add_edge("build_research_package", "draft_event_dossier")
    graph.add_edge("draft_event_dossier", "review_event_dossier")
    graph.add_edge("review_event_dossier", "revise_if_needed")
    graph.add_conditional_edges(
        "revise_if_needed",
        _route_after_revision_check,
        {
            "draft_event_dossier": "draft_event_dossier",
            "publish_or_manual_review": "publish_or_manual_review",
        },
    )
    graph.add_edge("publish_or_manual_review", "record_run")
    graph.add_edge("record_run", END)
    return graph.compile()


def _collect_signals_node(tools: EventPipelineTools):
    """创建 collect_signals 节点。

    输入：EventPipelineTools。
    输出：接收并返回 workflow state dict 的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """启动本轮 pipeline run。

        输入：包含 run_key、signal_ids 和 source_scope 的状态。
        输出：写入 run_id、running 状态和当前节点的状态。
        """
        parsed = EventPipelineState.model_validate(state)
        run = tools.start_run(parsed.run_key or "manual-p1-2-run", parsed.source_scope)
        return {
            **parsed.model_dump(),
            "run_id": run.id,
            "current_node": "collect_signals",
            "status": "running",
        }

    return node


def _normalize_signals_node(tools: EventPipelineTools):
    """创建 normalize_signals 节点。

    输入：EventPipelineTools。
    输出：校验来源信号存在并标记当前节点的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """校验并标记来源信号。

        输入：包含 signal_ids 的状态。
        输出：确认信号存在后的状态。
        """
        parsed = EventPipelineState.model_validate(state)
        tools.load_signals(parsed.signal_ids)
        return {**parsed.model_dump(), "current_node": "normalize_signals"}

    return node


def _editorial_triage_node(tools: EventPipelineTools):
    """创建 editorial_triage 节点。

    输入：EventPipelineTools。
    输出：记录值班编辑 stub 输出的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """执行值班编辑初筛。

        输入：包含 run_id 和 signal_ids 的状态。
        输出：追加 editor agent trace 的状态。
        """
        parsed = EventPipelineState.model_validate(state)
        signals = tools.load_signals(parsed.signal_ids)
        draft = tools.editor.triage(signals)
        if parsed.run_id is not None:
            tools.record_agent_result(
                parsed.run_id,
                tools.editor.name,
                "editor",
                f"triage {len(signals)} source signals",
                draft.model_dump(),
            )
        return {
            **parsed.model_dump(),
            "current_node": "editorial_triage",
            "agent_trace": [*parsed.agent_trace, {"node": "editorial_triage", "output": draft.model_dump()}],
        }

    return node


def _merge_and_rank_events_node(tools: EventPipelineTools):
    """创建 merge_and_rank_events 节点。

    输入：EventPipelineTools。
    输出：创建候选事件并写入 candidate_ids 的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """创建或更新候选事件。

        输入：包含 signal_ids 的状态。
        输出：写入 candidate_ids 的状态。
        """
        parsed = EventPipelineState.model_validate(state)
        signals = tools.load_signals(parsed.signal_ids)
        candidate = tools.create_candidate(signals)
        return {
            **parsed.model_dump(),
            "candidate_ids": [candidate.id],
            "current_node": "merge_and_rank_events",
        }

    return node


def _build_research_package_node():
    """创建 build_research_package 节点。

    输入：无。
    输出：只记录当前节点的轻量节点函数，P1-2 暂不新建 research package 表。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """标记研究材料组装完成。

        输入：当前 workflow state。
        输出：追加 research package trace 的状态。
        """
        parsed = EventPipelineState.model_validate(state)
        return {
            **parsed.model_dump(),
            "current_node": "build_research_package",
            "agent_trace": [
                *parsed.agent_trace,
                {"node": "build_research_package", "signal_count": len(parsed.signal_ids)},
            ],
        }

    return node


def _draft_event_dossier_node(tools: EventPipelineTools):
    """创建 draft_event_dossier 节点。

    输入：EventPipelineTools。
    输出：保存事件档案并记录 writer agent run 的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """生成事件档案草案。

        输入：包含 candidate_ids、signal_ids 和 revision_count 的状态。
        输出：写入 dossier_id 的状态。
        """
        parsed = EventPipelineState.model_validate(state)
        candidate = _load_current_candidate(tools.session, parsed)
        signals = tools.load_signals(parsed.signal_ids)
        revision_instruction = _last_revision_instruction(parsed)
        dossier = tools.create_dossier(candidate, signals, revision_instruction)
        if parsed.run_id is not None:
            tools.record_agent_result(
                parsed.run_id,
                tools.writer.name,
                "writer",
                f"draft dossier for candidate {candidate.id}",
                {
                    "dossier_id": dossier.id,
                    "card_title": dossier.card_title,
                    "detail_title": dossier.detail_title,
                },
                candidate_id=candidate.id,
                dossier_id=dossier.id,
                retry_count=parsed.revision_count,
            )
        return {
            **parsed.model_dump(),
            "dossier_id": dossier.id,
            "current_node": "draft_event_dossier",
            "agent_trace": [*parsed.agent_trace, {"node": "draft_event_dossier", "dossier_id": dossier.id}],
        }

    return node


def _review_event_dossier_node(tools: EventPipelineTools):
    """创建 review_event_dossier 节点。

    输入：EventPipelineTools。
    输出：保存审稿结果并记录 reviewer agent run 的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """审阅事件档案。

        输入：包含 dossier_id 和 revision_count 的状态。
        输出：写入 review_id 和 review_decision 的状态。
        """
        parsed = EventPipelineState.model_validate(state)
        if parsed.dossier_id is None:
            raise ValueError("dossier_id is required before review")
        event_dossier = tools.session.get(EventDossier, parsed.dossier_id)
        if event_dossier is None:
            raise ValueError(f"EventDossier not found for id={parsed.dossier_id}")
        review = tools.review_dossier(event_dossier, revision_count=parsed.revision_count)
        if parsed.run_id is not None:
            tools.record_agent_result(
                parsed.run_id,
                tools.reviewer.name,
                "reviewer",
                f"review dossier {event_dossier.id}",
                {
                    "review_id": review.id,
                    "decision": review.decision,
                    "risk_level": review.risk_level,
                    "issues": review.issues,
                },
                candidate_id=event_dossier.candidate_id,
                dossier_id=event_dossier.id,
                retry_count=parsed.revision_count,
            )
        return {
            **parsed.model_dump(),
            "review_id": review.id,
            "review_decision": review.decision,
            "current_node": "review_event_dossier",
            "agent_trace": [
                *parsed.agent_trace,
                {"node": "review_event_dossier", "review_id": review.id, "decision": review.decision},
            ],
        }

    return node


def _revise_if_needed_node():
    """创建 revise_if_needed 节点。

    输入：无。
    输出：根据 review_decision 更新 revision_count 或状态的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """判断是否需要修订。

        输入：包含 review_decision 和 revision_count 的状态。
        输出：需要修订时递增 revision_count，否则保持状态。
        """
        parsed = EventPipelineState.model_validate(state)
        if parsed.review_decision == "revise" and parsed.revision_count < 2:
            return {
                **parsed.model_dump(),
                "revision_count": parsed.revision_count + 1,
                "current_node": "revise_if_needed",
            }
        return {**parsed.model_dump(), "current_node": "revise_if_needed"}

    return node


def _publish_or_manual_review_node(tools: EventPipelineTools):
    """创建 publish_or_manual_review 节点。

    输入：EventPipelineTools。
    输出：发布事件或进入人工处理状态的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """根据审稿结果发布或转人工。

        输入：包含 candidate、dossier 和 review decision 的状态。
        输出：写入 published_event_id 和最终业务状态的状态。
        """
        parsed = EventPipelineState.model_validate(state)
        candidate_id = _current_candidate_id(parsed)
        if parsed.dossier_id is None:
            raise ValueError("dossier_id is required before publish")
        published = tools.publish_if_approved(candidate_id, parsed.dossier_id, parsed.review_decision or "")
        if published is not None:
            return {
                **parsed.model_dump(),
                "published_event_id": published.id,
                "current_node": "publish_or_manual_review",
                "status": "succeeded",
            }
        if parsed.review_decision == "reject":
            return {**parsed.model_dump(), "current_node": "publish_or_manual_review", "status": "failed"}
        return {**parsed.model_dump(), "current_node": "publish_or_manual_review", "status": "manual_review"}

    return node


def _record_run_node(tools: EventPipelineTools):
    """创建 record_run 节点。

    输入：EventPipelineTools。
    输出：回填 PipelineRun 计数并结束运行的节点函数。
    """

    def node(state: dict[str, Any]) -> dict[str, Any]:
        """结束本轮 pipeline run。

        输入：包含 run_id 和最终业务状态的状态。
        输出：当前节点变为 record_run 的最终状态。
        """
        parsed = EventPipelineState.model_validate(state)
        if parsed.run_id is None:
            raise ValueError("run_id is required before record_run")
        run_status = "succeeded" if parsed.status == "succeeded" else "partial_failed"
        if parsed.status == "failed":
            run_status = "failed"
        tools.finish_run_with_counts(parsed.run_id, status=run_status, summary=f"P1-2 workflow {parsed.status}")
        return {**parsed.model_dump(), "current_node": "record_run"}

    return node


def _route_after_revision_check(state: dict[str, Any]) -> str:
    """决定修订节点后的下一步。

    输入：当前 workflow state dict。
    输出：下一个节点名称。
    """
    parsed = EventPipelineState.model_validate(state)
    if parsed.review_decision == "revise" and parsed.revision_count <= 2:
        return "draft_event_dossier"
    return "publish_or_manual_review"


def _load_current_candidate(session: Session, state: EventPipelineState) -> EventCandidate:
    """读取当前候选事件。

    输入：Session 和包含 candidate_ids 的状态。
    输出：当前 EventCandidate ORM 对象。
    """
    candidate_id = _current_candidate_id(state)
    candidate = session.get(EventCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"EventCandidate not found for id={candidate_id}")
    return candidate


def _current_candidate_id(state: EventPipelineState) -> str:
    """读取当前候选事件 ID。

    输入：workflow state。
    输出：第一个 candidate_id；不存在时抛出 ValueError。
    """
    if not state.candidate_ids:
        raise ValueError("candidate_ids is required")
    return state.candidate_ids[0]


def _last_revision_instruction(state: EventPipelineState) -> str:
    """读取最近一次审稿修订意见。

    输入：workflow state 的 agent_trace。
    输出：最近 review 节点的修订说明；没有时返回空字符串。
    """
    for item in reversed(state.agent_trace):
        if item.get("node") == "review_event_dossier":
            output = item.get("output") or {}
            instruction = output.get("revision_instructions")
            if instruction:
                return str(instruction)
    return ""
