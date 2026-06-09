from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMClient:
    """LLM 底座占位类。

    输入：provider、model、可选 api_key/base_url。
    输出：当前后端 P1 不直接调用真实 LLM，因此方法会明确抛出未实现异常。
    """

    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None

    def chat(self, messages: list[dict[str, str]]) -> str:
        """同步聊天接口占位。

        输入：OpenAI-compatible 风格的 messages。
        输出：本轮后端只使用确定性 Agent stub，调用该方法会抛出 `NotImplementedError`。
        """
        raise NotImplementedError("Backend P1 uses deterministic Agent stubs; real LLM calls are out of scope.")

    def stream_chat(self, messages: list[dict[str, str]]):
        """流式聊天接口占位。

        输入：OpenAI-compatible 风格的 messages。
        输出：本轮后端不做真实流式 LLM 调用，调用该方法会抛出 `NotImplementedError`。
        """
        raise NotImplementedError("Backend P1 uses deterministic Agent stubs; real LLM calls are out of scope.")
