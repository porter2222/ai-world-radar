from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMClient:
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None

    def chat(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError("Backend P1 uses deterministic Agent stubs; real LLM calls are out of scope.")

    def stream_chat(self, messages: list[dict[str, str]]):
        raise NotImplementedError("Backend P1 uses deterministic Agent stubs; real LLM calls are out of scope.")
