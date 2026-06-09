from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    worker_root = Path(__file__).resolve().parents[1]
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))

from worker.config import load_settings


ProviderName = str
ChatMessage = dict[str, str]


@dataclass(frozen=True)
class LLMProviderConfig:
    """OpenAI-compatible provider 配置。"""

    provider: ProviderName
    model: str
    api_key: str
    base_url: str


class LLMClient:
    """LLM 底座。

    输入：provider、model、api_key、base_url，以及可选注入 client。
    输出：OpenAI-compatible chat / stream_chat 调用能力。
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        client=None,
    ) -> None:
        settings = load_settings()
        resolved_provider = provider or settings.llm_provider
        config = resolve_provider_config(
            provider=resolved_provider,
            model=model or settings.llm_model,
            api_key=api_key,
            base_url=base_url,
        )
        self.provider = config.provider
        self.model = config.model
        self.api_key = config.api_key
        self.base_url = config.base_url
        self.client = client or _create_openai_client(config)

    def chat(
        self,
        message: str | list[ChatMessage],
        system_prompt: str = "You are a helpful assistant.",
    ) -> str:
        """同步聊天接口。

        输入：字符串 message 或调用方已组装好的 messages。
        输出：模型返回的第一条文本内容。
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=_normalize_messages(message, system_prompt),
            stream=False,
        )
        return response.choices[0].message.content or ""

    def stream_chat(self, messages: list[ChatMessage]) -> Iterable[str]:
        """流式聊天接口。

        输入：OpenAI-compatible messages。
        输出：逐段 yield 模型 delta 文本。
        """
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
        )
        for event in stream:
            if not getattr(event, "choices", None):
                continue
            delta = getattr(event.choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if content:
                yield content


def resolve_provider_config(
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProviderConfig:
    """解析 provider 对应的 OpenAI-compatible 配置。"""
    if provider == "qwen-cn":
        return LLMProviderConfig(
            provider=provider,
            model=model or "qwen-plus",
            api_key=_required_api_key(api_key, "DASHSCOPE_API_KEY", provider),
            base_url=base_url or os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
    if provider == "deepseek":
        return LLMProviderConfig(
            provider=provider,
            model=model or "deepseek-chat",
            api_key=_required_api_key(api_key, "DEEPSEEK_API_KEY", provider),
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    if provider == "openai":
        return LLMProviderConfig(
            provider=provider,
            model=model or "gpt-4o-mini",
            api_key=_required_api_key(api_key, "OPENAI_API_KEY", provider),
            base_url=base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
    raise ValueError(f"Unsupported provider: {provider}")


def _required_api_key(explicit_key: str | None, env_name: str, provider: str) -> str:
    key = explicit_key or os.getenv(env_name)
    if not key:
        raise ValueError(f"Missing API key for provider '{provider}'. Set {env_name} in local environment.")
    return key


def _create_openai_client(config: LLMProviderConfig):
    from openai import OpenAI

    return OpenAI(api_key=config.api_key, base_url=config.base_url)


def _normalize_messages(message: str | list[ChatMessage], system_prompt: str) -> list[ChatMessage]:
    if isinstance(message, str):
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]
    return message


if __name__ == "__main__":
    print("LLMClient module loaded.")
    print("For local config smoke, run: python scripts/smoke_llm_client.py")
