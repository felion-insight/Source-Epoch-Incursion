from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


_user_settings_mod: object | bool | None = None


def _load_user_settings():
    """可选：`narrative_ai/user_settings.py`（从 user_settings.example.py 复制）。不纳入版本控制。"""
    global _user_settings_mod
    if _user_settings_mod is False:
        return None
    if _user_settings_mod is not None:
        return _user_settings_mod
    path = Path(__file__).resolve().parent / "user_settings.py"
    if not path.is_file():
        _user_settings_mod = False
        return None
    spec = importlib.util.spec_from_file_location("narrative_ai_user_settings", path)
    if spec is None or spec.loader is None:
        _user_settings_mod = False
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _user_settings_mod = mod
    return mod


def _from_user(attr: str, *aliases: str) -> str | None:
    mod = _load_user_settings()
    if mod is None:
        return None
    for name in (attr,) + aliases:
        if hasattr(mod, name):
            v = getattr(mod, name)
            if v is None:
                continue
            s = str(v).strip()
            if s:
                return s
    return None


def _read_api_base() -> str:
    env = os.environ.get("NARRATIVE_AI_BASE_URL")
    if env is not None and str(env).strip():
        return str(env).strip().rstrip("/")
    u = _from_user("NARRATIVE_AI_BASE_URL", "API_BASE")
    if u:
        return u.rstrip("/")
    return "http://35.220.164.252:3888".rstrip("/")


def _read_model() -> str:
    env = os.environ.get("NARRATIVE_AI_MODEL")
    if env is not None and str(env).strip():
        return str(env).strip()
    u = _from_user("NARRATIVE_AI_MODEL", "MODEL")
    if u:
        return u
    return "gpt-4o-mini"


def _read_api_key() -> str | None:
    env = os.environ.get("NARRATIVE_AI_API_KEY")
    if env is not None and str(env).strip():
        return str(env).strip()
    u = _from_user("NARRATIVE_AI_API_KEY", "API_KEY")
    return u or None


def _read_timeout() -> float:
    env = os.environ.get("NARRATIVE_AI_TIMEOUT")
    if env is not None and str(env).strip():
        return float(env)
    mod = _load_user_settings()
    if mod is not None and hasattr(mod, "NARRATIVE_AI_TIMEOUT"):
        v = getattr(mod, "NARRATIVE_AI_TIMEOUT")
        if v is not None and str(v).strip():
            return float(v)
    return 120.0


def _read_max_retries() -> int:
    env = os.environ.get("NARRATIVE_AI_MAX_RETRIES")
    if env is not None and str(env).strip():
        return int(env)
    mod = _load_user_settings()
    if mod is not None and hasattr(mod, "NARRATIVE_AI_MAX_RETRIES"):
        v = getattr(mod, "NARRATIVE_AI_MAX_RETRIES")
        if v is not None and str(v).strip():
            return int(v)
    return 3


def _read_retry_backoff_base() -> float:
    env = os.environ.get("NARRATIVE_AI_RETRY_BACKOFF_BASE")
    if env is not None and str(env).strip():
        return float(env)
    mod = _load_user_settings()
    if mod is not None and hasattr(mod, "NARRATIVE_AI_RETRY_BACKOFF_BASE"):
        v = getattr(mod, "NARRATIVE_AI_RETRY_BACKOFF_BASE")
        if v is not None and str(v).strip():
            return float(v)
    return 1.5


def _read_dry_run() -> bool:
    if os.environ.get("NARRATIVE_AI_DRY_RUN") is not None:
        return _env_bool("NARRATIVE_AI_DRY_RUN", False)
    mod = _load_user_settings()
    if mod is not None and hasattr(mod, "NARRATIVE_AI_DRY_RUN"):
        v = getattr(mod, "NARRATIVE_AI_DRY_RUN")
        if isinstance(v, bool):
            return v
        if v is not None and str(v).strip():
            return str(v).strip().lower() in {"1", "true", "yes", "on"}
    return False


@dataclass(frozen=True)
class Settings:
    """运行时配置：优先读环境变量 `NARRATIVE_AI_*`；未设置时读 `narrative_ai/user_settings.py`（见 user_settings.example.py）。"""

    api_base: str = field(default_factory=_read_api_base)
    model: str = field(default_factory=_read_model)
    api_key: str | None = field(default_factory=_read_api_key)
    timeout_seconds: float = field(default_factory=_read_timeout)
    max_retries: int = field(default_factory=_read_max_retries)
    retry_backoff_base: float = field(default_factory=_read_retry_backoff_base)
    dry_run: bool = field(default_factory=_read_dry_run)

    @property
    def chat_completions_url(self) -> str:
        return f"{self.api_base}/v1/chat/completions"
