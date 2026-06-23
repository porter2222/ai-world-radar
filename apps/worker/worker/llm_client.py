from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    worker_root = Path(__file__).resolve().parents[1]
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))

from worker.config import load_settings


ProviderName = str
ChatMessage = dict[str, str]


@dataclass(frozen=True)
class LLMProviderConfig:
    """OpenAI-compatible provider 配置。

    输入：provider、model、api_key、base_url，以及可选 User-Agent 覆盖。
    输出：创建 OpenAI SDK client 所需的完整配置对象。
    """

    provider: ProviderName
    model: str
    api_key: str
    base_url: str
    user_agent: str | None = None
    timeout_seconds: float | None = None


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
        """初始化 LLMClient。

        输入：可选 provider/model/api_key/base_url 覆盖项，以及测试可注入的 client。
        输出：带 provider、model、api_key、base_url 和 SDK client 的 LLMClient 实例。
        """
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
        self.last_usage: dict[str, int] | None = None

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
        self.last_usage = _extract_token_usage(response)
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
    """解析 provider 对应的 OpenAI-compatible 配置。

    输入：provider 名称，以及可选 model/api_key/base_url 覆盖项。
    输出：可用于创建 OpenAI SDK client 的 LLMProviderConfig。
    """
    if provider == "qwen-cn":
        return LLMProviderConfig(
            provider=provider,
            model=model or "qwen-plus",
            api_key=_required_api_key(api_key, "DASHSCOPE_API_KEY", provider),
            base_url=base_url or os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            timeout_seconds=_optional_request_timeout(),
        )
    if provider == "deepseek":
        return LLMProviderConfig(
            provider=provider,
            model=model or "deepseek-chat",
            api_key=_required_api_key(api_key, "DEEPSEEK_API_KEY", provider),
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout_seconds=_optional_request_timeout(),
        )
    if provider == "openai":
        return LLMProviderConfig(
            provider=provider,
            model=model or "gpt-4o-mini",
            api_key=_required_api_key(api_key, "OPENAI_API_KEY", provider),
            base_url=base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            user_agent=os.getenv("OPENAI_USER_AGENT") or None,
            timeout_seconds=_optional_request_timeout(),
        )
    raise ValueError(f"Unsupported provider: {provider}")


def _required_api_key(explicit_key: str | None, env_name: str, provider: str) -> str:
    """读取 provider API key。

    输入：显式传入的 key、环境变量名和 provider 名称。
    输出：可用 API key；缺失时抛出带 provider/env 提示的 ValueError。
    """
    key = explicit_key or os.getenv(env_name)
    if not key:
        raise ValueError(f"Missing API key for provider '{provider}'. Set {env_name} in local environment.")
    return key


def _optional_request_timeout() -> float | None:
    """读取可选 LLM 请求超时配置。

    输入：环境变量 LLM_REQUEST_TIMEOUT_SECONDS。
    输出：未配置时返回 None；已配置时返回正数秒数，非法值抛出 ValueError。
    """
    raw_timeout = os.getenv("LLM_REQUEST_TIMEOUT_SECONDS")
    if raw_timeout is None or raw_timeout.strip() == "":
        return None
    timeout_seconds = float(raw_timeout)
    if timeout_seconds <= 0:
        raise ValueError("LLM_REQUEST_TIMEOUT_SECONDS must be greater than 0.")
    return timeout_seconds


def _create_openai_client(config: LLMProviderConfig):
    """创建 OpenAI SDK client。

    输入：已解析好的 provider 配置。
    输出：可执行 chat.completions.create 的 OpenAI client；若配置 user_agent，会写入 default_headers。
    """
    from openai import OpenAI

    kwargs = {"api_key": config.api_key, "base_url": config.base_url}
    if config.user_agent:
        kwargs["default_headers"] = {"User-Agent": config.user_agent}
    if config.timeout_seconds is not None:
        kwargs["timeout"] = config.timeout_seconds
    return OpenAI(**kwargs)


def _normalize_messages(message: str | list[ChatMessage], system_prompt: str) -> list[ChatMessage]:
    """统一 OpenAI-compatible messages 格式。

    输入：字符串 message 或已组装 messages，以及默认 system_prompt。
    输出：可直接传给 chat.completions.create 的 messages 列表。
    """
    if isinstance(message, str):
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]
    return message


def _extract_token_usage(response: Any) -> dict[str, int] | None:
    """从 OpenAI-compatible 响应中提取 token usage。

    输入：OpenAI SDK response，可能带有 usage 属性或字典字段。
    输出：标准 prompt/completion/total token dict；缺失时返回 None。
    """
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
    else:
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        return None
    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }


if __name__ == "__main__":
    print("LLMClient module loaded.")
    print("For local config smoke, run: python scripts/smoke_llm_client.py")
