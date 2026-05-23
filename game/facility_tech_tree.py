"""设施科技升级树（DAG）：对齐 docs/sim_facility_tech_and_resource_gameplay.md §3。

节点数据字段（策划表 → JSON）：
- tech_id: 唯一键
- facility_id: 设施ID
- label_zh: UI标题
- body_zh: 风险提示/叙事摘要
- parent_tech_ids: 前置节点
- unlocks_management_tag: 关联经营标签
- mutually_exclusive_group: 互斥组
- sandbox_policy_override: 沙盒策略覆盖
- map_highlight: 大地图高亮
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TechNode:
    """单个科技树节点。"""

    tech_id: str
    facility_id: str
    label_zh: str
    parent_tech_ids: list[str] = field(default_factory=list)
    unlocks_management_tag: str | None = None
    mutually_exclusive_group: str | None = None
    sandbox_policy_override: str | None = None  # "allow" | "queue" | "block_ui"
    map_highlight: bool = False
    body_zh: str = ""


# 通讯阵列科技树
COMM_TECH_TREE: list[TechNode] = [
    TechNode(
        tech_id="comm_root",
        facility_id="comm",
        label_zh="通讯阵列（基础）",
        body_zh="与外部基地通讯、交易资源的核心设施。",
    ),
    TechNode(
        tech_id="comm_encrypt_v1",
        facility_id="comm",
        label_zh="加密破解模块 I",
        parent_tech_ids=["comm_root"],
        unlocks_management_tag="comm_array_encrypt",
        sandbox_policy_override="queue",
        map_highlight=True,
        body_zh="安装后可破译曙光议会的加密通讯，得知「灰镜」监视计划。",
    ),
    TechNode(
        tech_id="comm_broadcast_v1",
        facility_id="comm",
        label_zh="全频广播系统 I",
        parent_tech_ids=["comm_root"],
        unlocks_management_tag="comm_array_broadcast",
        sandbox_policy_override="queue",
        map_highlight=True,
        body_zh="向全球发送信息，但会吸引净空会的注意。",
    ),
    TechNode(
        tech_id="comm_encrypt_v2",
        facility_id="comm",
        label_zh="加密破解模块 II",
        parent_tech_ids=["comm_encrypt_v1"],
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="增强解码能力，获取更多议会内部通讯。",
    ),
    TechNode(
        tech_id="comm_deep_monitor",
        facility_id="comm",
        label_zh="深度监控阵列",
        parent_tech_ids=["comm_broadcast_v1"],
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="追踪回声集团的频段活动。",
    ),
]

# 源矿机科技树
MINE_TECH_TREE: list[TechNode] = [
    TechNode(
        tech_id="mine_root",
        facility_id="mine",
        label_zh="源矿机（基础）",
        body_zh="从海底源矿脉中提取能源的基础设施。",
    ),
    TechNode(
        tech_id="mine_deepen_v1",
        facility_id="mine",
        label_zh="深层开采协议",
        parent_tech_ids=["mine_root"],
        unlocks_management_tag="mine_deepen",
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="加大开采深度，能源产出+40，但岸线侵入加速20%。",
    ),
    TechNode(
        tech_id="mine_limit_v1",
        facility_id="mine",
        label_zh="限产稳定协议",
        parent_tech_ids=["mine_root"],
        unlocks_management_tag="mine_limit",
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="限制开采，岸线侵入减缓10%，但能源产出下降。",
    ),
    TechNode(
        tech_id="mine_efficiency",
        facility_id="mine",
        label_zh="高效抽取模块",
        parent_tech_ids=["mine_root"],
        mutually_exclusive_group="mine_mode",
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="在不加深开采的情况下优化提取效率。",
    ),
    TechNode(
        tech_id="mine_safety",
        facility_id="mine",
        label_zh="矿区安全加固",
        parent_tech_ids=["mine_root"],
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="降低矿区事故概率，提升设施稳定性。",
    ),
]

# 医疗/研究实验室科技树
LAB_TECH_TREE: list[TechNode] = [
    TechNode(
        tech_id="lab_root",
        facility_id="lab",
        label_zh="医疗/研究实验室（基础）",
        body_zh="治疗伤员、研发药物的基地核心设施。",
    ),
    TechNode(
        tech_id="lab_neural_scan",
        facility_id="lab",
        label_zh="神经扫描仪",
        parent_tech_ids=["lab_root"],
        unlocks_management_tag="lab_neural_scan",
        sandbox_policy_override="queue",
        map_highlight=True,
        body_zh="可检测NPC体内隐藏的监控芯片，揭露卡伦的真实身份。",
    ),
    TechNode(
        tech_id="lab_sync_suppressor",
        facility_id="lab",
        label_zh="同调抑制器",
        parent_tech_ids=["lab_root"],
        unlocks_management_tag="lab_sync_suppressor",
        sandbox_policy_override="queue",
        map_highlight=True,
        body_zh="降低玩家同调值，延缓与源的接触。",
    ),
    TechNode(
        tech_id="lab_advanced_drug",
        facility_id="lab",
        label_zh="高级药剂合成",
        parent_tech_ids=["lab_root"],
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="提升医疗物资产出效率。",
    ),
    TechNode(
        tech_id="lab_analysis",
        facility_id="lab",
        label_zh="源样本分析",
        parent_tech_ids=["lab_root"],
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="对源矿样本进行深度分析，获取情报。",
    ),
]

# 防御工事科技树
DEFENSE_TECH_TREE: list[TechNode] = [
    TechNode(
        tech_id="defense_root",
        facility_id="defense",
        label_zh="防御工事（基础）",
        body_zh="延缓岸线侵入、保护基地的核心防线。",
    ),
    TechNode(
        tech_id="defense_fortify",
        facility_id="defense",
        label_zh="防御工事强化",
        parent_tech_ids=["defense_root"],
        unlocks_management_tag="defense_fortify",
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="提升至坚固等级，岸线侵入进度减慢30%。",
    ),
    TechNode(
        tech_id="defense_auto_turret",
        facility_id="defense",
        label_zh="自动防御炮台",
        parent_tech_ids=["defense_root"],
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="自动攻击接近岸线的异常体。",
    ),
    TechNode(
        tech_id="defense_advanced",
        facility_id="defense",
        label_zh="前沿防御矩阵",
        parent_tech_ids=["defense_fortify"],
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="构建多层防御体系，大幅延缓侵入。",
    ),
]

# 地下监听站科技树
LISTEN_TECH_TREE: list[TechNode] = [
    TechNode(
        tech_id="listen_root",
        facility_id="listen",
        label_zh="地下监听站（建造中）",
        body_zh="聆听「源的低语」的特殊设施，需要大量能源建造。",
    ),
    TechNode(
        tech_id="listen_station_on",
        facility_id="listen",
        label_zh="监听站启用",
        parent_tech_ids=["listen_root"],
        unlocks_management_tag="listen_station_on",
        sandbox_policy_override="queue",
        map_highlight=True,
        body_zh="建造并启用地下监听站，大幅提升情报获取，但同调值飙升。",
    ),
    TechNode(
        tech_id="listen_deep",
        facility_id="listen",
        label_zh="深度聆听协议",
        parent_tech_ids=["listen_station_on"],
        sandbox_policy_override="allow",
        map_highlight=True,
        body_zh="接收更远处的源低语，获取更多先驱文明记忆片段。",
    ),
]

# 所有科技树的映射
FACILITY_TECH_TREES: dict[str, list[TechNode]] = {
    "comm": COMM_TECH_TREE,
    "mine": MINE_TECH_TREE,
    "lab": LAB_TECH_TREE,
    "defense": DEFENSE_TECH_TREE,
    "listen": LISTEN_TECH_TREE,
}


def get_tech_tree(facility_id: str) -> list[TechNode]:
    """获取指定设施的科技树。"""
    return FACILITY_TECH_TREES.get(facility_id, [])


def get_tech_node(facility_id: str, tech_id: str) -> TechNode | None:
    """获取指定设施的指定科技节点。"""
    for node in get_tech_tree(facility_id):
        if node.tech_id == tech_id:
            return node
    return None


def get_root_nodes(facility_id: str) -> list[TechNode]:
    """获取指定设施的根节点（无前置的节点）。"""
    return [n for n in get_tech_tree(facility_id) if not n.parent_tech_ids]


def get_child_nodes(facility_id: str, tech_id: str) -> list[TechNode]:
    """获取指定节点的子节点。"""
    return [
        n
        for n in get_tech_tree(facility_id)
        if tech_id in n.parent_tech_ids
    ]


def get_parent_nodes(facility_id: str, tech_id: str) -> list[TechNode]:
    """获取指定节点的前置节点。"""
    node = get_tech_node(facility_id, tech_id)
    if not node:
        return []
    return [
        get_tech_node(facility_id, pid)
        for pid in node.parent_tech_ids
        if get_tech_node(facility_id, pid)
    ]


def is_tech_unlocked(
    tech_id: str,
    applied_tags: set[str],
    pending_tags: set[str] | None = None,
) -> bool:
    """检查科技节点是否已解锁（前置已满足）。"""
    node = None
    for tree_nodes in FACILITY_TECH_TREES.values():
        for n in tree_nodes:
            if n.tech_id == tech_id:
                node = n
                break
        if node:
            break

    if not node:
        return False

    # 根节点总是解锁
    if not node.parent_tech_ids:
        return True

    # 检查前置节点
    all_tags = applied_tags | (pending_tags or set())
    for parent_id in node.parent_tech_ids:
        parent = None
        for tree_nodes in FACILITY_TECH_TREES.values():
            for n in tree_nodes:
                if n.tech_id == parent_id:
                    parent = n
                    break
            if parent:
                break
        if not parent:
            continue
        # 如果前置节点解锁了管理标签，检查标签是否已应用
        if parent.unlocks_management_tag:
            if parent.unlocks_management_tag not in all_tags:
                return False
        else:
            # 如果前置节点不关联标签，递归检查
            if not is_tech_unlocked(parent_id, applied_tags, pending_tags):
                return False
    return True


def is_tech_researched(
    tech_id: str,
    applied_tags: set[str],
) -> bool:
    """检查科技节点是否已研究（其关联标签已应用）。"""
    node = get_tech_node_for_id(tech_id)
    if not node:
        return False
    if node.unlocks_management_tag:
        return node.unlocks_management_tag in applied_tags
    # 非叶子节点：检查是否所有前置都已研究
    for parent_id in node.parent_tech_ids:
        if not is_tech_researched(parent_id, applied_tags):
            return False
    return True


def get_tech_node_for_id(tech_id: str) -> TechNode | None:
    """通过tech_id查找节点（跨所有设施）。"""
    for tree_nodes in FACILITY_TECH_TREES.values():
        for n in tree_nodes:
            if n.tech_id == tech_id:
                return n
    return None


def build_tech_tree_payload(
    facility_id: str,
    applied_tags: set[str],
    pending_tags: set[str] | None = None,
    sandbox_phase: bool = False,
) -> dict[str, Any]:
    """构建供前端使用的科技树payload。"""
    nodes = get_tech_tree(facility_id)
    all_tags = applied_tags | (pending_tags or set())

    def node_to_dict(node: TechNode) -> dict[str, Any]:
        unlocked = is_tech_unlocked(node.tech_id, applied_tags, pending_tags)
        researched = is_tech_researched(node.tech_id, applied_tags)

        # 确定沙盒策略
        pol = node.sandbox_policy_override
        if sandbox_phase and pol is None:
            pol = "queue"  # 默认在沙盒中排队
        blocked_reason = ""
        if sandbox_phase and pol == "block_ui":
            blocked_reason = "静默运营期内暂不开放该项立项。"
        elif sandbox_phase and pol == "queue":
            blocked_reason = "该决议将在退出静默期后生效。"

        return {
            "tech_id": node.tech_id,
            "facility_id": node.facility_id,
            "label_zh": node.label_zh,
            "body_zh": node.body_zh,
            "parent_tech_ids": node.parent_tech_ids,
            "unlocks_management_tag": node.unlocks_management_tag,
            "mutually_exclusive_group": node.mutually_exclusive_group,
            "map_highlight": node.map_highlight,
            "unlocked": unlocked,
            "researched": researched,
            "blocked_reason_zh": blocked_reason,
        }

    # 构建节点映射
    node_map = {n.tech_id: node_to_dict(n) for n in nodes}

    # 添加子节点引用
    for tech_id, ndict in node_map.items():
        ndict["child_tech_ids"] = [
            nid for nid, nd in node_map.items() if tech_id in nd["parent_tech_ids"]
        ]

    # 构建层级（从根开始BFS）
    roots = [n for n in nodes if not n.parent_tech_ids]
    levels: list[list[str]] = []
    visited: set[str] = set()

    current_level = [n.tech_id for n in roots]
    while current_level:
        levels.append(current_level)
        visited.update(current_level)
        next_level: list[str] = []
        for tid in current_level:
            for child in get_child_nodes(facility_id, tid):
                if child.tech_id not in visited and child.tech_id not in next_level:
                    if is_tech_unlocked(child.tech_id, applied_tags, pending_tags):
                        next_level.append(child.tech_id)
        current_level = next_level

    return {
        "facility_id": facility_id,
        "nodes": node_map,
        "levels": levels,
        "root_tech_ids": [n.tech_id for n in roots],
    }


FACILITY_TECH_LABEL_ZH: dict[str, str] = {
    "comm": "通讯阵列",
    "mine": "源矿区",
    "lab": "医疗实验室",
    "defense": "海岸防线",
    "listen": "地下监听站",
}


def build_facility_tech_hints_for_sandbox(sess: Any) -> list[dict[str, Any]]:
    """静默 HUD 短文：各设施尚有未立项的科技叶数量（不整张铺树以降低 payload）。"""
    if str(getattr(sess, "story_phase", "") or "").strip() != "Sandbox":
        return []
    applied = frozenset(getattr(sess, "applied_management_tags", []) or [])
    pending = frozenset(getattr(sess, "management_queue_pending", []) or [])
    out: list[dict[str, Any]] = []
    for fid in FACILITY_TECH_TREES:
        payload = build_tech_tree_payload(fid, applied, pending, sandbox_phase=True)
        actionable = sum(
            1
            for n in payload["nodes"].values()
            if n.get("unlocked")
            and not n.get("researched")
            and n.get("unlocks_management_tag")
        )
        total = len(payload["nodes"])
        researched_count = sum(1 for n in payload["nodes"].values() if n.get("researched"))
        out.append(
            {
                "facility_id": fid,
                "facility_label_zh": FACILITY_TECH_LABEL_ZH.get(fid, fid),
                "pending_research_count": actionable,
                "nodes_researched": researched_count,
                "nodes_total": total,
            }
        )
    return out
