"""经营决议完成后的轻量叙事挂钩（不改变节点 ID，仅补 plot flag / 伏笔）。"""

from __future__ import annotations

from .session import GameSession


def apply_management_narrative_hooks(sess: GameSession, tag: str) -> None:
    nid = sess.current_node_id
    if tag == "comm_array_encrypt" and nid == "01-05":
        sess.plot.enable("echo_route_hint")
