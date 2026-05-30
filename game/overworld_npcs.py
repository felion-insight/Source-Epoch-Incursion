"""大地图角色：文档中的出现条件 + 表面/隐藏身份展示（隐藏仅在剧情揭示后显示）。"""

from __future__ import annotations

from typing import Any

from narrative_ai.loader import get_npc

from .npc_roaming import npc_roaming_row
from .session import GameSession

# 伊丽莎白：文档「仅远程/全息」——大地图实体点仅在相关剧情节点出现
_ELIZABETH_MAP_NODES: frozenset[str] = frozenset(
    {
        "02-07",
        "02-08",
        "03-01",
        "03-02",
        "03-03",
        "03-04",
        "03-05",
        "03-06",
        "FIN-01",
        "FIN-02",
        "FIN-03",
    }
)


def _done(sess: GameSession, node_id: str) -> bool:
    return node_id in sess.completed_nodes


def _impression_from_trust(trust: float) -> str:
    if trust >= 78:
        return "印象：高度信任，愿把后背交给你。"
    if trust >= 60:
        return "印象：认可你的指挥，会主动透露更多现场细节。"
    if trust >= 45:
        return "印象：保持职业距离，仍在评估你的立场。"
    if trust >= 30:
        return "印象：戒备较强，措辞偏生硬。"
    return "印象：信任偏低，可能拒绝深谈。"


def npc_visible_on_map(sess: GameSession, npc_id: str) -> bool:
    """是否与 docs/npc_bible 中的「出现条件」一致的大地图显示。"""
    nid = sess.current_node_id
    focus = set(sess.current_node().npc_focus)

    if npc_id == "echo_7":
        # 文档：同调>30% 后可在屏幕出现；通讯阵列加密线（01-05）或第一幕大事件后也可出现
        # 补充：若当前节点的 npc_focus 包含 echo_7，则剧情焦点即回声-7，理应可见
        return (
            npc_id in focus
            or sess.plot.has("echo_route_hint")
            or float(sess.hidden.SYNC) > 30
            or _done(sess, "01-07")
            or sess.conspiracy_tier_unlocked >= 1
        )

    if npc_id == "klein":
        # 文档：深层真相持有者，地下实验室线索后更合理出现
        return _done(sess, "02-04") or nid.startswith("03-") or sess.conspiracy_tier_unlocked >= 2

    if npc_id == "elizabeth":
        return "elizabeth" in focus or nid in _ELIZABETH_MAP_NODES or sess.conspiracy_tier_unlocked >= 2

    # 卡伦、林博士、小胖、堇：序章/第一幕起常驻基地
    return True


def _show_hidden_identity(sess: GameSession, npc_id: str) -> bool:
    """是否可在 UI 中展示「隐藏身份」一行（防剧透：仅剧情推进后）。"""
    if npc_id == "karen":
        return bool(sess.hidden.karen_defected) or _done(sess, "02-05")
    if npc_id == "dr_lin":
        return sess.conspiracy_tier_unlocked >= 1 or _done(sess, "02-01")
    if npc_id == "chubby":
        return bool(sess.hidden.chubby_quest_complete) or _done(sess, "02-04")
    if npc_id == "jin":
        return _done(sess, "02-07") or float(sess.hidden.PURIFY) >= 38
    if npc_id == "echo_7":
        return sess.conspiracy_tier_unlocked >= 2 or float(sess.hidden.ECHO) >= 35
    if npc_id == "klein":
        return _done(sess, "03-02") or sess.conspiracy_tier_unlocked >= 3
    if npc_id == "elizabeth":
        return sess.conspiracy_tier_unlocked >= 2 or _done(sess, "02-07")
    return False


def overworld_npc_rows(sess: GameSession) -> list[dict[str, Any]]:
    """供 GET /api/state 注入客户端：可见性 + 身份文案。"""
    rows: list[dict[str, Any]] = []
    for npc_id in ("karen", "dr_lin", "chubby", "jin", "echo_7", "klein", "elizabeth"):
        sheet = get_npc(npc_id)
        visible = npc_visible_on_map(sess, npc_id)
        show_h = _show_hidden_identity(sess, npc_id)
        surface = str(sheet.get("role_surface", "")).strip()
        hidden = str(sheet.get("role_hidden", "")).strip()
        roam = npc_roaming_row(sess, npc_id)
        store = sess.get_memory_store(npc_id)
        trust_v = float(store.emotional.trust)
        notes = list(store.long_term_notes or [])[-5:]
        rows.append(
            {
                "id": npc_id,
                "visible": visible,
                "name": str(sheet.get("display_name", npc_id)),
                "surface_line": surface,
                "hidden_line": hidden if show_h else None,
                "roaming_slug": roam["slug"],
                "roaming_location_zh": roam["location_zh"],
                "trust": round(trust_v, 1),
                "impression_zh": _impression_from_trust(trust_v),
                "memory_fragments_zh": notes,
            }
        )
    return rows


def opening_player_context(sess: GameSession, npc_id: str, *, story_focus: bool) -> str:
    """打开对话时自动 AI 生成用的用户侧情境（一次请求）。"""
    sheet = get_npc(npc_id)
    name = str(sheet.get("display_name", npc_id))
    n = sess.current_node()
    must = "\n".join(f"- {t}" for t in sess.get_active_must_deliver_zh())
    store = sess.get_memory_store(npc_id)
    trust = float(store.emotional.trust)
    tier = int(sess.conspiracy_tier_unlocked)

    if story_focus:
        return (
            f"你是《源纪元·岸线侵入》角色【{name}】，人设与约束以系统角色卡为准。\n"
            f"当前关键节点：{n.id}《{n.title_zh}》。已知阴谋层上限：{tier}。你对玩家的信任约 {trust:.0f}/100。\n"
            f"必达信息（须在语气与信息中自然落实，勿像念清单）：\n{must}\n"
            "任务：代理指挥官刚走到你面前。请直接输出角色台词（可含极短动作括号），共 2～5 句，"
            "交代此刻现场态势、气氛与最紧迫的一两件事。不要跳出角色，不要写系统说明；"
            "不要剧透超过当前阴谋层上限的真相。"
        )

    return (
        f"你是【{name}】，人设以系统角色卡为准。\n"
        f"当前主线剧情焦点在别的角色/节点（当前节点 {n.id}《{n.title_zh}》）。\n"
        "玩家在大地图路过与你搭话。请输出 2～4 句日常向台词，可带基地琐事或情绪反应；"
        "勿剧透未解锁阴谋；若你的隐藏身份尚未被剧情揭示，不要主动自曝。"
    )
