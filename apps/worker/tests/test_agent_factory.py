from worker.agents.event_pipeline_agents import (
    OnDutyEditorAgentStub,
    ResearchWriterAgentStub,
    ReviewPublisherAgentStub,
)
from worker.agents.factory import create_event_agents
from worker.agents.llm_event_pipeline_agents import (
    OnDutyEditorLLMAgent,
    ResearchWriterLLMAgent,
    ReviewPublisherLLMAgent,
)


class FakeLLMClient:
    """测试用 fake LLM client。

    输入：无。
    输出：带 provider/model 标识的可共享 fake client。
    """

    provider = "fake"
    model = "fake-model"

    def chat(self, message: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """模拟 LLMClient.chat。

        输入：user message 和 system_prompt。
        输出：空 JSON；本测试只验证 factory 注入，不触发真实调用。
        """
        return "{}"


def test_create_event_agents_defaults_to_llm_mode_with_shared_client():
    """验证默认 agent mode 是 llm。

    输入：不传 mode，只传入测试 fake LLM client。
    输出：三类 LLM Agent，且共享同一个 fake client。
    """
    fake_client = FakeLLMClient()

    agents = create_event_agents(llm_client=fake_client)

    assert isinstance(agents.editor, OnDutyEditorLLMAgent)
    assert isinstance(agents.writer, ResearchWriterLLMAgent)
    assert isinstance(agents.reviewer, ReviewPublisherLLMAgent)
    assert agents.editor.llm_client is fake_client
    assert agents.writer.llm_client is fake_client
    assert agents.reviewer.llm_client is fake_client


def test_create_event_agents_explicit_stub_mode_for_offline_tests():
    """验证 stub 只作为显式离线测试模式保留。

    输入：mode=stub。
    输出：三类确定性 stub agent。
    """
    agents = create_event_agents(mode="stub")

    assert isinstance(agents.editor, OnDutyEditorAgentStub)
    assert isinstance(agents.writer, ResearchWriterAgentStub)
    assert isinstance(agents.reviewer, ReviewPublisherAgentStub)


def test_create_event_agents_llm_mode_returns_llm_agents_with_shared_client():
    """验证 llm mode 创建三类真实 LLM Agent。

    输入：mode=llm 和一个 fake LLM client。
    输出：三类 LLM Agent，且共享同一个 fake client。
    """
    fake_client = FakeLLMClient()

    agents = create_event_agents(mode="llm", llm_client=fake_client)

    assert isinstance(agents.editor, OnDutyEditorLLMAgent)
    assert isinstance(agents.writer, ResearchWriterLLMAgent)
    assert isinstance(agents.reviewer, ReviewPublisherLLMAgent)
    assert agents.editor.llm_client is fake_client
    assert agents.writer.llm_client is fake_client
    assert agents.reviewer.llm_client is fake_client
