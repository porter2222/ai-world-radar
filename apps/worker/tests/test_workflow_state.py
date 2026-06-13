import pytest
from pydantic import ValidationError

from worker.schemas.workflow import EventPipelineState


def test_workflow_state_tracks_ids_status_and_revision_count():
    """验证工作流状态能记录节点、ID 和修订次数。

    输入：run_id、signal_ids、candidate_id、dossier_id、当前节点和修订次数。
    输出：Pydantic state 保留这些字段，并拒绝超过 P1 上限的修订次数。
    """
    state = EventPipelineState(
        run_id="run_1",
        signal_ids=["sig_1"],
        candidate_ids=["cand_1"],
        dossier_id="dos_1",
        current_node="review_event_dossier",
        revision_count=2,
        status="running",
    )

    assert state.run_id == "run_1"
    assert state.signal_ids == ["sig_1"]
    assert state.candidate_ids == ["cand_1"]
    assert state.dossier_id == "dos_1"
    assert state.revision_count == 2

    with pytest.raises(ValidationError):
        EventPipelineState(revision_count=3)


def test_workflow_state_rejects_unknown_fields():
    """验证工作流状态禁止未知字段。

    输入：包含 unexpected 字段的 state。
    输出：Pydantic 抛出 ValidationError，防止节点随意塞入未约定状态。
    """
    with pytest.raises(ValidationError):
        EventPipelineState(unexpected=True)
