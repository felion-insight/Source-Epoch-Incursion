"""大地图 / 设施与剧情节点、经营标签的对应（对齐 docs 叙事与经营设计）。"""

from __future__ import annotations

from .session import GameSession
from .sim_sandbox import sandbox_policy

# 剧情节点 / 设施 → 选择 ID 的映射（玩家走访对应设施时触发单一确认按钮）
# 指挥中心（command）通常可展示全部选项（UI 层通过 node_id 判断）
NODE_FACILITY_CHOICES: dict[str, dict[str, str]] = {
    "01-02": {
        "comm": "upg_comm",
        "mine": "upg_mine",
        "lab": "upg_lab",
    },
    "PRO-02": {
        "defense": "pro02_defense",
        "lab": "pro02_rescue",
    },
}

# 向后兼容：保留旧名称为 01-02 映射
FACILITY_TO_UPGRADE_CHOICE: dict[str, str] = NODE_FACILITY_CHOICES.get("01-02", {})

# 设施上的「经营深化」标签（与 narrative_ai.management 键一致）

# 大地图设施「当前剧情相关」提示（供 UI 高亮；与节点焦点弱耦合）
COMMAND_ANCHOR_NODES: frozenset[str] = frozenset(
    {
        "PRO-01",
        "PRO-02",
        "01-06",
        "01-07",
        "02-02",
        "02-05",
        "02-06",
        "02-07",
        "02-08",
        "03-05",
        "03-06",
        "FIN-01",
        "FIN-02",
    }
)
LAB_ANCHOR_NODES: frozenset[str] = frozenset(
    {"01-01", "01-03", "01-04", "02-01", "02-02", "02-03", "02-04", "02-05"}
)
COMM_ANCHOR_NODES: frozenset[str] = frozenset({"01-05", "02-07", "02-08", "03-06"})
DEFENSE_ANCHOR_NODES: frozenset[str] = frozenset({"PRO-02", "01-07", "03-05"})
MINE_ANCHOR_NODES: frozenset[str] = frozenset({"01-02", "01-03", "02-03", "02-04"})
HELIPAD_ANCHOR_NODES: frozenset[str] = frozenset({"02-07", "02-08", "03-06", "FIN-01"})
LISTEN_ANCHOR_NODES: frozenset[str] = frozenset({"PRO-04", "03-03"})
PURIFY_ANCHOR_NODES: frozenset[str] = frozenset({"01-06", "02-08", "03-06"})
SUNK_LAB_ANCHOR_NODES: frozenset[str] = frozenset({"03-01", "03-02", "03-04"})

FACILITY_MANAGEMENT_TAGS: dict[str, list[dict[str, str]]] = {
    "comm": [
        {"tag": "comm_array_encrypt", "label_zh": "安装加密破解模块"},
        {"tag": "comm_array_broadcast", "label_zh": "安装全频广播系统"},
    ],
    "mine": [
        {"tag": "mine_deepen", "label_zh": "加大开采深度"},
        {"tag": "mine_limit", "label_zh": "限制开采"},
    ],
    "lab": [
        {"tag": "lab_neural_scan", "label_zh": "加装神经扫描仪"},
        {"tag": "lab_sync_suppressor", "label_zh": "研发同调抑制器"},
    ],
    "defense": [
        {"tag": "defense_fortify", "label_zh": "防御工事提升至坚固"},
    ],
    "listen": [
        {"tag": "listen_station_on", "label_zh": "地下监听站：建造并启用（叙事向大额消耗）"},
    ],
    "command": [
        {"tag": "supply_medical_first", "label_zh": "资源倾斜：后勤优先伤员救治"},
    ],
    "helipad": [
        {"tag": "accept_echo_aid", "label_zh": "接洽：接受回声集团能源补给"},
        {"tag": "reject_echo_aid", "label_zh": "回绝回声集团的「援助礼包」"},
    ],
    "purify_grove": [
        {"tag": "purge_partial_mine", "label_zh": "净空会方案：同意局部引爆矿区（高危）"},
    ],
    "sunk_lab": [],
}


def _build_management_tag_home_facility() -> dict[str, str]:
    out: dict[str, str] = {}
    for fid, rows in FACILITY_MANAGEMENT_TAGS.items():
        for r in rows:
            t = str(r.get("tag") or "").strip()
            if t:
                out[t] = fid
    return out


MANAGEMENT_TAG_HOME_FACILITY: dict[str, str] = _build_management_tag_home_facility()


def narrative_gate_management_decision_zh(sess: GameSession, tag: str) -> str | None:
    """剧情阶段门闩：返回中文原因表示 UI 不应展示且 POST /api/management 须拒绝。"""
    t = (tag or "").strip()
    if not t:
        return "无效的经营决议标签"

    phase = str(getattr(sess, "story_phase", "StoryBeat") or "StoryBeat").strip()
    if phase == "Sandbox":
        pol = sandbox_policy(t)
        if pol == "block_ui":
            return "静默运营期内暂不开放该项立项。"
        return None

    nid = sess.current_node_id
    # 节点正在等待设施决策时，禁止单独立项
    if nid in NODE_FACILITY_CHOICES:
        return "当前为剧情决策节点：请先在指挥中心或对应设施内完成剧情选项，勿单独深化立项。"
    fid = MANAGEMENT_TAG_HOME_FACILITY.get(t)
    if not fid:
        return None
    if not facility_relevant_to_node(sess, fid):
        return "当前剧情阶段与该设施的经营决议无关，无法立项。"
    if t == "comm_array_encrypt" and nid != "01-05":
        return "加密破解模块仅在通讯阵列加密相关剧情节点开放立项。"
    return None


def upgrade_choice_for_facility(sess: GameSession, facility_id: str) -> str | None:
    """返回走访 facility_id 时对应的单一选择 ID（用于「在此确认」按钮），无映射则返回 None。"""
    return NODE_FACILITY_CHOICES.get(sess.current_node_id, {}).get(facility_id)


def npc_is_current_focus(sess: GameSession, npc_id: str) -> bool:
    return npc_id in sess.current_node().npc_focus


def facility_relevant_to_node(sess: GameSession, facility_id: str) -> bool:
    nid = sess.current_node_id
    # 节点有设施→选择映射时，直接根据映射判相关
    mapping = NODE_FACILITY_CHOICES.get(nid)
    if mapping:
        return facility_id in mapping or (facility_id == "command")
    if nid in LISTEN_ANCHOR_NODES:
        return facility_id == "listen"
    anchor_map: dict[str, frozenset[str]] = {
        "command": COMMAND_ANCHOR_NODES,
        "lab": LAB_ANCHOR_NODES,
        "comm": COMM_ANCHOR_NODES,
        "defense": DEFENSE_ANCHOR_NODES,
        "mine": MINE_ANCHOR_NODES,
        "helipad": HELIPAD_ANCHOR_NODES,
        "purify_grove": PURIFY_ANCHOR_NODES,
        "sunk_lab": SUNK_LAB_ANCHOR_NODES,
    }
    nodes = anchor_map.get(facility_id)
    return bool(nodes and nid in nodes)
