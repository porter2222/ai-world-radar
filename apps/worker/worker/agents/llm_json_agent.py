from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMAgentOutputError(ValueError):
    """表示 LLM 输出无法解析为目标 schema。

    输入：解析或校验失败的错误说明。
    输出：供 workflow 或脚本层捕获的业务异常。
    """


@dataclass(frozen=True)
class LLMJsonResult(Generic[SchemaT]):
    """封装一次结构化 LLM 调用结果。

    输入：Pydantic payload、模型原始文本、重试次数、耗时、token usage 和可选 prompt 版本。
    输出：供具体 Agent 节点读取的结构化结果对象。
    """

    payload: SchemaT
    raw_text: str
    retry_count: int
    duration_ms: int
    token_usage: dict[str, int] | None = None
    prompt_version: str | None = None


class LLMJsonAgent:
    """真实 LLM Agent 的结构化 JSON 调用基座。

    输入：具备 chat 方法的 LLM client 和最大修复次数。
    输出：把模型文本解析并校验为目标 Pydantic schema 的能力。
    """

    def __init__(self, llm_client, max_retries: int = 2):
        """初始化 JSON Agent 基座。

        输入：LLMClient 或测试 fake client，以及最大 repair 重试次数。
        输出：可复用的 LLMJsonAgent 实例。
        """
        self.llm_client = llm_client
        self.max_retries = max_retries
        self.last_duration_ms: int | None = None
        self.last_token_usage: dict[str, int] | None = None

    def run_json(
        self,
        schema_type: type[SchemaT],
        *,
        system_prompt: str,
        user_prompt: str,
        prompt_version: str | None = None,
    ) -> LLMJsonResult[SchemaT]:
        """调用模型并返回结构化 JSON。

        输入：目标 Pydantic schema、system prompt、user prompt 和可选 prompt version。
        输出：通过 schema 校验的 LLMJsonResult；多次失败后抛出 LLMAgentOutputError。
        """
        message = user_prompt
        last_error = ""
        raw_text = ""
        started_at = time.perf_counter()
        token_usage: dict[str, int] | None = None
        for attempt in range(self.max_retries + 1):
            raw_text = self.llm_client.chat(message, system_prompt=system_prompt)
            token_usage = _merge_token_usage(token_usage, _normalize_token_usage(getattr(self.llm_client, "last_usage", None)))
            try:
                payload = self._validate_payload(schema_type, raw_text)
                duration_ms = _elapsed_ms(started_at)
                self.last_duration_ms = duration_ms
                self.last_token_usage = token_usage
                return LLMJsonResult(
                    payload=payload,
                    raw_text=raw_text,
                    retry_count=attempt,
                    duration_ms=duration_ms,
                    token_usage=token_usage,
                    prompt_version=prompt_version,
                )
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = str(exc)
                if attempt >= self.max_retries:
                    break
                message = self._build_repair_prompt(
                    schema_type=schema_type,
                    original_prompt=user_prompt,
                    raw_text=raw_text,
                    error_message=last_error,
                )

        self.last_duration_ms = _elapsed_ms(started_at)
        self.last_token_usage = token_usage
        raise LLMAgentOutputError(f"无法解析 LLM 输出为 {schema_type.__name__}: {last_error}")

    def _validate_payload(self, schema_type: type[SchemaT], raw_text: str) -> SchemaT:
        """解析并校验模型输出。

        输入：目标 schema 类型和模型原始文本。
        输出：通过 `model_validate` 的 Pydantic 对象。
        """
        data = json.loads(_extract_json_text(raw_text))
        return schema_type.model_validate(data)

    def _build_repair_prompt(
        self,
        *,
        schema_type: type[SchemaT],
        original_prompt: str,
        raw_text: str,
        error_message: str,
    ) -> str:
        """构造 JSON 修复提示。

        输入：目标 schema、原始任务、模型原文和错误摘要。
        输出：要求模型只返回合法 JSON 的修复 prompt。
        """
        return (
            "请修复上一轮输出，使其成为可以被解析和校验的 JSON。\n"
            f"目标 schema: {schema_type.__name__}\n"
            f"错误摘要: {error_message}\n"
            f"原始任务: {original_prompt}\n"
            f"上一轮输出:\n{raw_text}\n"
            "只返回 JSON，不要解释，不要使用 Markdown。"
        )


def _extract_json_text(raw_text: str) -> str:
    """从模型原文中提取 JSON 文本。

    输入：模型原始文本，可为纯 JSON、fenced JSON 或夹杂说明的文本。
    输出：可传给 `json.loads` 的 JSON 字符串；找不到对象时返回清理后的原文。
    """
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def _elapsed_ms(started_at: float) -> int:
    """计算从开始时间到当前的毫秒耗时。

    输入：`time.perf_counter()` 记录的开始时间。
    输出：非负整数毫秒。
    """
    return max(0, int((time.perf_counter() - started_at) * 1000))


def _normalize_token_usage(usage: Any) -> dict[str, int] | None:
    """归一化 LLM client 暴露的 token usage。

    输入：None、dict 或带 prompt_tokens/completion_tokens/total_tokens 属性的对象。
    输出：标准 usage dict；缺失时返回 None。
    """
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


def _merge_token_usage(
    current: dict[str, int] | None,
    incoming: dict[str, int] | None,
) -> dict[str, int] | None:
    """累加多次 LLM 调用的 token usage。

    输入：当前累计 usage 和本次调用 usage。
    输出：新的累计 usage；两者都缺失时返回 None。
    """
    if incoming is None:
        return current
    if current is None:
        return dict(incoming)
    return {
        "prompt_tokens": current.get("prompt_tokens", 0) + incoming.get("prompt_tokens", 0),
        "completion_tokens": current.get("completion_tokens", 0) + incoming.get("completion_tokens", 0),
        "total_tokens": current.get("total_tokens", 0) + incoming.get("total_tokens", 0),
    }
