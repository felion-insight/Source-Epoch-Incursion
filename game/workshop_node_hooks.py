"""剧情节点 → 基地核心自动化设施蓝图/贸易等解锁钩子。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session import GameSession
    from .story_graph import NodeSpec


def apply_workshop_node_hooks(sess: "GameSession", node: "NodeSpec") -> None:
    from .underground_workshop import grant_blueprint_from_story

    completed = frozenset(getattr(sess, "completed_nodes", []) or [])
    nid = str(node.id or "").strip()

    # 第一幕中期：完成「升级优先」会议（01-02）后，小胖提示地下空间
    if nid == "01-04" and "01-02" in completed:
        grant_blueprint_from_story(
            sess,
            "物资短缺会议后，小胖提起基地核心中有一处闲置空间，也许能改造成自动化产线。",
        )

    if nid in {"01-07", "02-01"} and completed & frozenset({"01-02", "01-04"}):
        grant_blueprint_from_story(
            sess,
            "基地档案中补录了自动化设施蓝图条目，可前往基地核心察看。",
            silent_if_known=True,
        )
