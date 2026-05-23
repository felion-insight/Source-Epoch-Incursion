"""进程内单例会话（Web API 与调试共用）。"""

from __future__ import annotations

import threading

from .session import GameSession

_sess: GameSession = GameSession()
_sess_lock = threading.RLock()


def get_session() -> GameSession:
    return _sess


def set_session(s: GameSession) -> None:
    global _sess
    _sess = s


def session_lock() -> threading.RLock:
    """串行化会话读写，避免 ThreadingHTTPServer 多线程下剧情状态竞态。"""
    return _sess_lock
