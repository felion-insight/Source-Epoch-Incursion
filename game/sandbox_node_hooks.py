"""进入剧情节点后与静默运营相位的钩子（对齐 story_nodes.schema）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .story_graph import NodeSpec

if TYPE_CHECKING:
    from .session import GameSession


def apply_node_sandbox_automation(sess: "GameSession", node: NodeSpec) -> None:
    """在 enter_current（含 on_enter_* 写入）末尾调用。"""
    from .sim_sandbox import append_bulletin_zh

    if not node.sandbox_enter_after_beat:
        return
    if str(getattr(sess, "story_phase", "StoryBeat") or "").strip() != "StoryBeat":
        return
    # 避免终局误入静默（仍可在 FIN-01 显式启用）
    if str(node.act or "").strip() == "finale" and node.id != "FIN-01":
        return

    sess.sandbox_ops_unlocked = True
    setattr(sess, "story_phase", "Sandbox")
    sess.sandbox_generation = int(getattr(sess, "sandbox_generation", 0) or 0) + 1
    sess.sandbox_enter_world_day = int(getattr(sess, "world_day", 1) or 1)

    raw_min = node.sandbox_enter_min_world_days
    if raw_min is None:
        setattr(sess, "sandbox_min_world_days", None)
    else:
        sess.sandbox_min_world_days = max(0, int(raw_min))

    append_bulletin_zh(
        sess,
        f"一段波折暂告平息——基地进入日常运营节律。",
    )
