from __future__ import annotations

import json
import random
import time
from typing import Any

import urllib.error
import urllib.request

from narrative_ai.config import Settings
from narrative_ai.schemas import ChatCompletionRequest

# 需要重试的瞬态 HTTP 状态码
RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
# 响应体中"服务器过载"类关键词（用于 200 以外的任何响应码辅助判断）
OVERLOAD_KEYWORDS: tuple[str, ...] = ("cpu_overloaded", "overloaded", "rate_limit", "too_many_requests")


def _is_retryable_http_error(code: int, body_text: str) -> bool:
    """判断是否为可重试的 HTTP 错误。"""
    if code in RETRYABLE_HTTP_CODES:
        return True
    # 有些代理用 200 返回错误，检查响应体关键词
    lower = body_text.lower()
    return any(kw in lower for kw in OVERLOAD_KEYWORDS)


def _sleep_with_jitter(base_delay: float, attempt: int) -> float:
    """指数退避 + 随机抖动，返回实际休眠秒数。"""
    delay = base_delay * (2 ** (attempt - 1))
    jitter = delay * random.uniform(0.1, 0.5)
    actual = delay + jitter
    time.sleep(actual)
    return actual


class ChatClient:
    """OpenAI-compatible chat client，内置指数退避重试。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or Settings()

    def complete(self, req: ChatCompletionRequest) -> str:
        if self._s.dry_run:
            return (
                "（信道静默…源暂时无法回应。请稍后再试。）"
            )

        body = json.dumps(req.to_api_body(self._s.model)).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._s.api_key:
            headers["Authorization"] = f"Bearer {self._s.api_key}"

        last_error: Exception | None = None
        max_attempts = max(1, self._s.max_retries + 1)  # 至少试 1 次

        for attempt in range(1, max_attempts + 1):
            try:
                r = urllib.request.Request(
                    self._s.chat_completions_url,
                    data=body,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(r, timeout=self._s.timeout_seconds) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                    return self._extract_assistant_text(raw)

            except urllib.error.HTTPError as e:
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    err_body = ""
                code = e.code

                # 非瞬态错误直接抛出
                if not _is_retryable_http_error(code, err_body):
                    hint = ""
                    if code == 401:
                        hint = (
                            " 提示：服务端拒绝鉴权，请在环境中设置正确的 "
                            "NARRATIVE_AI_API_KEY（Bearer token）。"
                        )
                    raise RuntimeError(f"HTTP {code}: {err_body}{hint}") from e

                # 瞬态错误：重试
                last_error = RuntimeError(f"HTTP {code}: {err_body}")
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"AI API 调用失败（已重试 {self._s.max_retries} 次）：HTTP {code}: {err_body}"
                    ) from e
                waited = _sleep_with_jitter(self._s.retry_backoff_base, attempt)
                print(f"[ChatClient] HTTP {code} ← AI 后端，{waited:.1f}s 后第 {attempt + 1}/{max_attempts} 次重试…")

            except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as e:
                # 网络层错误（连接被拒、DNS 解析失败、超时等）
                last_error = e
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"AI API 网络错误（已重试 {self._s.max_retries} 次）：{e}"
                    ) from e
                waited = _sleep_with_jitter(self._s.retry_backoff_base, attempt)
                print(f"[ChatClient] 网络错误: {e}，{waited:.1f}s 后第 {attempt + 1}/{max_attempts} 次重试…")

        # 理论上不会走到这里，但兜底
        raise RuntimeError(
            f"AI API 调用失败：{last_error}"
        ) from last_error

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
