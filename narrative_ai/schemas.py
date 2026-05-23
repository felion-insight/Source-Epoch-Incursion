from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class ChatCompletionRequest:
    """Payload for POST /v1/chat/completions (OpenAI-compatible)."""

    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_api_body(self, default_model: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model or default_model,
            "messages": [{"role": m.role, "content": m.content} for m in self.messages],
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        body.update(self.extra)
        return body


# --- Game narrative domain (extend as your design doc solidifies) ---


@dataclass
class WorldContext:
    """Static or session world state you inject into prompts."""

    title: str = ""
    premise: str = ""
    tone: str = ""
    player_role: str = ""
    known_npcs: str = ""
    current_location: str = ""
    recent_events: str = ""
    constraints: str = ""  # e.g. no gore, stay canon


@dataclass
class BeatRequest:
    """One generation unit: e.g. next scene, branch, or dialogue block."""

    intent: str  # what you want the model to produce
    world: WorldContext
    format_hint: str = ""  # e.g. JSON keys, Ren'Py-like structure
    prior_summary: str = ""  # compressed story so far
