from __future__ import annotations

from typing import Any

from narrative_ai.config import Settings
from narrative_ai.openai_client import ChatClient
from narrative_ai.prompts import messages_for_beat
from narrative_ai.schemas import BeatRequest, ChatCompletionRequest, ChatMessage, Role


class NarrativeGenerator:
    """
    High-level entry: build prompts → call API → return assistant text.

    Later you can add: JSON schema validation, branching graphs, RAG over docs/, etc.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._client = ChatClient(self._settings)

    def generate_beat(self, beat: BeatRequest, *, temperature: float = 0.7, max_tokens: int | None = None) -> str:
        req = ChatCompletionRequest(
            messages=messages_for_beat(beat),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._client.complete(req)

    def generate_raw(
        self,
        messages: list[ChatMessage] | list[tuple[Role, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Pass ChatMessage list or (role, content) tuples for full control."""
        norm: list[ChatMessage]
        if messages and isinstance(messages[0], ChatMessage):
            norm = messages  # type: ignore[assignment]
        else:
            norm = [ChatMessage(role=r, content=c) for r, c in messages]  # type: ignore[union-attr]

        req = ChatCompletionRequest(
            messages=norm,
            temperature=temperature,
            max_tokens=max_tokens,
            extra=extra or {},
        )
        return self._client.complete(req)
