from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Literal, Optional
import os
import contextlib

# External SDKs
# OpenAI (>=1.40)
with contextlib.suppress(ImportError):
    from openai import OpenAI  # type: ignore

# Anthropic (>=0.34)
with contextlib.suppress(ImportError):
    import anthropic  # type: ignore


Role = Literal["system", "user", "assistant"]
ProviderName = Literal["OpenAI", "Anthropic", "Local Echo"]

@dataclass
class ChatMessage:
    role: Role
    content: str

# ---------- Base ----------
class BaseProvider:
    name: ProviderName
    default_model: str

    def __init__(self, model: str, temperature: float, max_tokens: int):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def stream_chat(self, messages: List[ChatMessage]) -> Iterator[str]:
        """Yield text deltas as they arrive."""
        raise NotImplementedError

# ---------- OpenAI ----------
class OpenAIProvider(BaseProvider):
    name: ProviderName = "OpenAI"
    default_model = "gpt-4o-mini"

    def __init__(self, model: str, temperature: float, max_tokens: int):
        super().__init__(model, temperature, max_tokens)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY in environment.")
        self.client = OpenAI(api_key=api_key)

    def stream_chat(self, messages: List[ChatMessage]) -> Iterator[str]:
        # Convert messages keeping system/user/assistant
        formatted = [{"role": m.role, "content": m.content} for m in messages]

        # Stream response
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=formatted,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        for event in stream:
            delta = event.choices[0].delta.content or ""
            if delta:
                yield delta

# ---------- Anthropic ----------
class AnthropicProvider(BaseProvider):
    name: ProviderName = "Anthropic"
    default_model = "claude-3-5-sonnet"

    def __init__(self, model: str, temperature: float, max_tokens: int):
        super().__init__(model, temperature, max_tokens)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY in environment.")
        self.client = anthropic.Anthropic(api_key=api_key)

    def stream_chat(self, messages: List[ChatMessage]) -> Iterator[str]:
        # Anthropic expects a single system string and an array of messages (user/assistant)
        system = "\n".join([m.content for m in messages if m.role == "system"]).strip() or None
        convo: List[dict] = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        with self.client.messages.stream(
            model=self.model,
            system=system,
            messages=convo,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ) as stream:
            for text in stream.text_stream:
                yield text

# ---------- Local Echo (for offline demo) ----------
class LocalEchoProvider(BaseProvider):
    name: ProviderName = "Local Echo"
    default_model = "echo-1"

    def stream_chat(self, messages: List[ChatMessage]) -> Iterator[str]:
        user_last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        out = f"[local-echo] You said: {user_last}"
        # simulate streaming
        for ch in out:
            yield ch

# ---------- Registry / Factory ----------
@dataclass
class ProviderInfo:
    default_model: str
    cls: type[BaseProvider]

PROVIDERS: Dict[ProviderName, ProviderInfo] = {
    "OpenAI": ProviderInfo(default_model=OpenAIProvider.default_model, cls=OpenAIProvider),
    "Anthropic": ProviderInfo(default_model=AnthropicProvider.default_model, cls=AnthropicProvider),
    "Local Echo": ProviderInfo(default_model=LocalEchoProvider.default_model, cls=LocalEchoProvider),
}

def build_provider(name: ProviderName, model: str, temperature: float, max_tokens: int) -> BaseProvider:
    info = PROVIDERS[name]
    return info.cls(model=model, temperature=temperature, max_tokens=max_tokens)
