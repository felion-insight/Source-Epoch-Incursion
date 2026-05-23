"""大地图「当前目标」：与编剧 must_deliver 分离，不向玩家暴露未揭露剧情。"""

from __future__ import annotations

from .session import GameSession
from .story_graph import NodeSpec

ACT_LABEL_ZH: dict[str, str] = {
    "prologue": "序幕",
    "act1": "第一幕",
    "act2": "第二幕",
    "act3": "第三幕",
    "finale": "终局",
}


def _act_label_zh(act: str) -> str:
    return ACT_LABEL_ZH.get(act, "主线")


def player_visible_objectives(node: NodeSpec) -> list[str]:
    """
    玩家可在 HUD 阅读的当前情境目标。
    若在 story_nodes.json 中配置了 player_objectives_zh 则优先使用；
    否则给出不引用 must_deliver 的泛化说明（节点名/幕别可作为位置签）。
    """
    if node.player_objectives_zh:
        return list(node.player_objectives_zh)
    act = _act_label_zh(node.act)
    return [
        f"当前剧情位置：「{node.title_zh}」（{act}）。",
        "通过大地图接触相关角色与设施，在对话与选项中推进；未在剧情中揭露的信息不会在此处预告。",
    ]


def prepend_sandbox_objectives_banner(phase: str, objectives: list[str]) -> list[str]:
    """当 story_phase == Sandbox 时为 HUD 增补运营向引导，不改变节点 JSON。"""
    if str(phase or "").strip() != "Sandbox":
        return objectives
    banner_zh = (
        "【静默运营期——基地玩法主导】主线推进已冻结。请以大面板「基地日 +1」驱动时钟："
        "每一日会结转物资与岸线压力、重置 NPC 交流配额；「决算」排队设施立项；签发野外远征归国入账；侧栏可进行「地图资源行动」自取四类资源。"
        "准备回到剧情时手动「结束静默」。"
    )
    return [banner_zh, *objectives]


def objectives_upcoming_blurb(sess: GameSession) -> str | None:
    """
    「后续」区：不列出未发生节点的标题或必达条，仅用分支数量/结构作元信息。
    """
    if str(getattr(sess, "story_phase", "StoryBeat") or "").strip() == "Sandbox":
        return (
            "静默期中：请以左侧「基地日推进」为主线节拍；侧栏可进行地图资源行动；野外远征归国与基地日结转绑定。"
            "不向玩家预告下一主线节点。"
        )
    g = sess.graph()
    n = sess.current_node()
    if n.id in ("FIN-02", "FIN-03"):
        return None
    ids: list[str] = []
    if n.choices:
        for c in n.choices:
            nxt = c.next if c.next is not None else n.next
            if nxt and nxt not in ids and nxt in g:
                ids.append(nxt)
    elif n.next and n.next in g:
        ids.append(n.next)
    if not ids:
        return None
    if len(ids) == 1:
        return "完成本段后，故事将按主线进入下一关键事件；具体情节在进入该段时自然呈现。"
    return (
        f"本节点将影响后续走向：当前可见约 {len(ids)} 条不同的剧情切入点，"
        "具体发展取决于你的选择（不在此预告尚未发生的剧情）。"
    )
