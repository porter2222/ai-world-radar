from worker.llm_client import LLMClient


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeChoice:
    def __init__(self, content: str):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse("detail json")


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeOpenAIClient:
    def __init__(self):
        self.chat = FakeChat()


def test_llm_client_sends_openai_compatible_chat_request():
    """验证 LLMClient 能把简单 message 转成 OpenAI-compatible chat 请求。

    输入：注入 fake OpenAI client、provider/model/api_key/base_url。
    输出：返回模型内容，并记录 model/messages/stream 参数。
    """
    fake_client = FakeOpenAIClient()
    client = LLMClient(
        provider="openai",
        model="gpt-test",
        api_key="test-key",
        base_url="https://example.test/v1",
        client=fake_client,
    )

    result = client.chat("写一段事件详情", system_prompt="你是 AI 情报编辑。")

    assert result == "detail json"
    call = fake_client.chat.completions.calls[0]
    assert call["model"] == "gpt-test"
    assert call["stream"] is False
    assert call["messages"] == [
        {"role": "system", "content": "你是 AI 情报编辑。"},
        {"role": "user", "content": "写一段事件详情"},
    ]


def test_llm_client_accepts_prebuilt_messages():
    """验证 LLMClient 能直接转发调用方组装好的 messages。

    输入：预组装 messages 和 fake client。
    输出：messages 不被额外包裹。
    """
    fake_client = FakeOpenAIClient()
    client = LLMClient(
        provider="deepseek",
        model="deepseek-chat",
        api_key="test-key",
        client=fake_client,
    )
    messages = [{"role": "user", "content": "hello"}]

    client.chat(messages)

    call = fake_client.chat.completions.calls[0]
    assert call["messages"] == messages


def test_worker_package_exports_llm_client():
    """验证本地手动脚本可使用 `from worker import LLMClient`。

    输入：worker 包级导入。
    输出：导出的 LLMClient 与真实类一致。
    """
    from worker import LLMClient as ExportedLLMClient

    assert ExportedLLMClient is LLMClient
