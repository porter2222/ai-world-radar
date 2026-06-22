import sys
from types import SimpleNamespace

from worker.llm_client import LLMClient, LLMProviderConfig, _create_openai_client, resolve_provider_config


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeChoice:
    def __init__(self, content: str):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str, usage=None):
        self.choices = [FakeChoice(content)]
        self.usage = usage


class FakeCompletions:
    def __init__(self):
        self.calls = []
        self.next_usage = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse("detail json", usage=self.next_usage)


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


def test_llm_client_exposes_token_usage_from_response():
    """验证 LLMClient 会保存 OpenAI-compatible 响应中的 usage。

    输入：fake OpenAI response.usage，包含 prompt/completion/total token。
    输出：chat 返回文本，同时 client.last_usage 保存标准 token usage dict。
    """
    fake_client = FakeOpenAIClient()
    fake_client.chat.completions.next_usage = SimpleNamespace(
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
    )
    client = LLMClient(
        provider="openai",
        model="gpt-test",
        api_key="test-key",
        base_url="https://example.test/v1",
        client=fake_client,
    )

    result = client.chat("写一段事件详情", system_prompt="你是 AI 情报编辑。")

    assert result == "detail json"
    assert client.last_usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def test_worker_package_exports_llm_client():
    """验证本地手动脚本可使用 `from worker import LLMClient`。

    输入：worker 包级导入。
    输出：导出的 LLMClient 与真实类一致。
    """
    from worker import LLMClient as ExportedLLMClient

    assert ExportedLLMClient is LLMClient


def test_openai_provider_config_reads_optional_user_agent(monkeypatch):
    """验证 OpenAI provider 会读取可选 User-Agent 覆盖。

    输入：OPENAI_API_KEY、OPENAI_BASE_URL 和 OPENAI_USER_AGENT 环境变量。
    输出：解析后的 provider config 携带 user_agent，供 SDK 初始化使用。
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.codexapi.space/v1")
    monkeypatch.setenv("OPENAI_USER_AGENT", "python-httpx/0.28.1")

    config = resolve_provider_config("openai")

    assert config.provider == "openai"
    assert config.base_url == "https://api.codexapi.space/v1"
    assert config.user_agent == "python-httpx/0.28.1"


def test_create_openai_client_passes_user_agent_as_default_header(monkeypatch):
    """验证 OpenAI SDK 初始化时会带上 User-Agent 覆盖。

    输入：携带 user_agent 的 LLMProviderConfig，以及 fake openai.OpenAI 构造器。
    输出：构造 OpenAI client 时传入 default_headers={"User-Agent": "..."}。
    """

    class FakeOpenAI:
        """记录 OpenAI SDK 初始化参数的 fake 构造器。

        输入：OpenAI SDK 构造参数。
        输出：保存 kwargs，便于测试断言。
        """

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    config = LLMProviderConfig(
        provider="openai",
        model="gpt-test",
        api_key="test-key",
        base_url="https://api.codexapi.space/v1",
        user_agent="python-httpx/0.28.1",
    )

    client = _create_openai_client(config)

    assert client.kwargs["api_key"] == "test-key"
    assert client.kwargs["base_url"] == "https://api.codexapi.space/v1"
    assert client.kwargs["default_headers"] == {"User-Agent": "python-httpx/0.28.1"}
