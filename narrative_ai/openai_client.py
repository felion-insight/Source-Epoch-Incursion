from __future__ import annotations

import json
from typing import Any

import urllib.error
import urllib.request

from narrative_ai.config import Settings
from narrative_ai.schemas import ChatCompletionRequest


class ChatClient:
    """Minimal OpenAI-compatible chat client (no extra dependencies)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or Settings()

    def complete(self, req: ChatCompletionRequest) -> str:
        if self._s.dry_run:
            return (
                "[NARRATIVE_AI_DRY_RUN=1] Placeholder: no HTTP request was made.\n"
                "本地占位：未调用 API。若需真实生成，请设置 NARRATIVE_AI_API_KEY，并取消 DRY_RUN。"
            )

        body = json.dumps(req.to_api_body(self._s.model)).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._s.api_key:
            headers["Authorization"] = f"Bearer {self._s.api_key}"

        r = urllib.request.Request(
            self._s.chat_completions_url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(r, timeout=self._s.timeout_seconds) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            hint = ""
            if e.code == 401:
                hint = (
                    " 提示：服务端拒绝鉴权，请在环境中设置正确的 NARRATIVE_AI_API_KEY（Bearer token）。"
                )
            raise RuntimeError(f"HTTP {e.code}: {err_body}{hint}") from e

        return self._extract_assistant_text(raw)

    @staticmethod
    def _extract_assistant_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(f"Unexpected API response (no choices): {payload}")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content is None:
            raise RuntimeError(f"Unexpected API response (no content): {payload}")
        if isinstance(content, str):
            return content
        # Some proxies return a list of parts
        if isinstance(content, list):
            parts: list[str] = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(str(p.get("text", "")))
            return "".join(parts)
        return str(content)
