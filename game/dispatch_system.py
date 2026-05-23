"""委任系统与设施状态：对齐 docs/management_sim_design.md 第6节与 sim_data_schema_content_authoring.md。

委任系统：玩家可选择NPC代管基地，根据NPC特性改变经济tick策略。
设施状态：设施拥有耐久/工况，影响产出效率。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 委任NPC列表
DISPATCHABLE_NPCS = frozenset({"karen", "dr_lin"})

DISPATCH_NPC_INFO: dict[str, dict[str, Any]] = {
    "karen": {
        "label_zh": "卡伦",
        "role_zh": "安全主管",
        "strategy_zh": "优先升级防御，限制开采",
        "description_zh": "卡伦倾向于保守策略：优先保障基地安全，限制能源产出以延缓岸线侵入。",
        "effect_modifiers": {
            "defense_fortify_likelihood": 0.8,  # 更可能升级防御
            "mine_limit_likelihood": 0.6,  # 更可能限制开采
            "mine_deepen_likelihood": 0.1,  # 几乎不会加大开采
        },
        "trust_change_on_dispatch": 5,  # 被委任时信任上升
    },
    "dr_lin": {
        "label_zh": "林博士",
        "role_zh": "首席科学家",
        "strategy_zh": "优先升级实验室，加大开采",
        "description_zh": "林博士倾向于研究策略：优先发展科研能力，适度加大能源开采以支持研究。",
        "effect_modifiers": {
            "defense_fortify_likelihood": 0.3,
            "mine_limit_likelihood": 0.2,
            "mine_deepen_likelihood": 0.7,  # 更可能加大开采
            "lab_upgrade_likelihood": 0.8,  # 更可能升级实验室
        },
        "trust_change_on_dispatch": 5,
    },
}


@dataclass
class DispatchSession:
    """当前委任会话状态。"""

    npc_id: str | None = None  # 当前委任的NPC
    dispatch_day: int = 0  # 开始委任的日期
    daily_decisions_log: list[dict[str, str]] = field(default_factory=list)


@dataclass
class FacilityStatus:
    """单个设施的状态。"""

    facility_id: str
    tier: int = 1  # 等级
    condition: int = 100  # 耐久/工况 0-100
    efficiency_mult: float = 1.0  # 效率修正
    branch_choice: str | None = None  # 分叉选择
    # 运行时状态
    is_active: bool = True  # 是否启用
    breakdown_risk: float = 0.0  # 故障风险


# 设施默认状态
DEFAULT_FACILITY_STATUS: dict[str, FacilityStatus] = {
    "comm": FacilityStatus(facility_id="comm", tier=1, condition=85, efficiency_mult=1.0),
    "mine": FacilityStatus(facility_id="mine", tier=1, condition=90, efficiency_mult=1.0),
    "lab": FacilityStatus(facility_id="lab", tier=1, condition=80, efficiency_mult=1.0),
    "defense": FacilityStatus(facility_id="defense", tier=1, condition=75, efficiency_mult=1.0),
    "listen": FacilityStatus(facility_id="listen", tier=0, condition=0, efficiency_mult=0.0, is_active=False),
}


def get_facility_default(facility_id: str) -> FacilityStatus:
    """获取设施默认状态。"""
    return DEFAULT_FACILITY_STATUS.get(
        facility_id,
        FacilityStatus(facility_id=facility_id, tier=1, condition=100, efficiency_mult=1.0),
    )


def calculate_daily_upkeep(
    facility_id: str,
    tier: int,
    condition: int,
) -> dict[str, int]:
    """计算设施每日维护消耗。"""
    base = {"comm": 2, "mine": 3, "lab": 2, "defense": 3, "listen": 4}
    base_cost = base.get(facility_id, 2)
    # 等级越高消耗越大
    tier_mult = 1.0 + (tier - 1) * 0.3
    # 工况越差效率越低
    condition_mult = max(0.5, condition / 100.0)
    return {
        "energy": int(base_cost * tier_mult * condition_mult),
        "food": int(base_cost * 0.5 * tier_mult * condition_mult),
    }


def simulate_dispatch_auto_decision(
    dispatcher_id: str,
    current_day: int,
    resources: dict[str, int],
    applied_tags: set[str],
) -> dict[str, Any] | None:
    """模拟委任NPC的自动决策（简化版）。"""
    info = DISPATCH_NPC_INFO.get(dispatcher_id)
    if not info:
        return None

    modifiers = info["effect_modifiers"]
    decisions_made = []

    # 检查是否应该做出防御升级决策
    if "defense_fortify" not in applied_tags:
        if resources.get("energy", 0) >= 40:
            if modifiers.get("defense_fortify_likelihood", 0) > 0.5:
                decisions_made.append({
                    "decision": "defense_fortify",
                    "label_zh": "防御工事提升至坚固",
                    "reason_zh": f"{info['label_zh']}认为需要加强防御",
                })

    # 检查开采决策
    if "mine_deepen" not in applied_tags and "mine_limit" not in applied_tags:
        energy = resources.get("energy", 0)
        if modifiers.get("mine_deepen_likelihood", 0) > 0.5 and energy >= 20:
            decisions_made.append({
                "decision": "mine_deepen",
                "label_zh": "加大开采深度",
                "reason_zh": f"{info['label_zh']}建议增加能源产出",
            })
        elif modifiers.get("mine_limit_likelihood", 0) > 0.5:
            decisions_made.append({
                "decision": "mine_limit",
                "label_zh": "限制开采",
                "reason_zh": f"{info['label_zh']}建议控制岸线侵入",
            })

    return {
        "dispatcher_id": dispatcher_id,
        "day": current_day,
        "decisions": decisions_made,
        "strategy_summary_zh": info["strategy_zh"],
    }


def apply_facility_condition_change(
    status: FacilityStatus,
    delta: int,
) -> tuple[int, str | None]:
    """应用设施状态变化，返回新状态和可能的事件。"""
    old_condition = status.condition
    status.condition = max(0, min(100, status.condition + delta))

    # 检查是否触发故障
    if status.condition < 30 and old_condition >= 30:
        status.breakdown_risk = 0.3
        return status.condition, f"{status.facility_id}设施工况严重下降，故障风险上升！"
    elif status.condition < 10:
        status.is_active = False
        status.efficiency_mult = 0.0
        return status.condition, f"{status.facility_id}设施已停机！"

    # 效率随状态变化
    status.efficiency_mult = status.condition / 100.0
    return status.condition, None


def get_facility_upgrade_cost(facility_id: str, current_tier: int) -> dict[str, int]:
    """获取设施升级到下一等级的消耗。"""
    base_costs = {
        "comm": {"energy": 30, "intel": 5},
        "mine": {"energy": 35, "food": 5},
        "lab": {"energy": 25, "medical": 10},
        "defense": {"energy": 40, "food": 8},
        "listen": {"energy": 50, "intel": 15},
    }
    costs = base_costs.get(facility_id, {"energy": 30})
    # 每级增加50%消耗
    mult = 1.0 + (current_tier - 1) * 0.5
    return {k: int(v * mult) for k, v in costs.items()}


def build_dispatch_status_payload(
    session: DispatchSession | None,
    current_day: int,
) -> dict[str, Any]:
    """构建委任状态payload。"""
    if session is None or session.npc_id is None:
        return {
            "is_dispatched": False,
            "dispatcher": None,
            "available_dispatchers": [
                {
                    "npc_id": npc_id,
                    "label_zh": info["label_zh"],
                    "role_zh": info["role_zh"],
                    "strategy_zh": info["strategy_zh"],
                    "description_zh": info["description_zh"],
                }
                for npc_id, info in DISPATCH_NPC_INFO.items()
            ],
        }

    info = DISPATCH_NPC_INFO.get(session.npc_id, {})
    days_active = current_day - session.dispatch_day
    return {
        "is_dispatched": True,
        "dispatcher": {
            "npc_id": session.npc_id,
            "label_zh": info.get("label_zh", ""),
            "role_zh": info.get("role_zh", ""),
            "strategy_zh": info.get("strategy_zh", ""),
            "days_active": days_active,
        },
        "recent_decisions": session.daily_decisions_log[-5:],
        "available_dispatchers": [
            {
                "npc_id": npc_id,
                "label_zh": info["label_zh"],
                "role_zh": info["role_zh"],
                "strategy_zh": info["strategy_zh"],
                "description_zh": info["description_zh"],
            }
            for npc_id, info in DISPATCH_NPC_INFO.items()
            if npc_id != session.npc_id
        ],
    }


def build_facility_status_payload(
    facilities: dict[str, FacilityStatus],
) -> dict[str, Any]:
    """构建设施状态payload。"""
    result = {}
    for fid, status in facilities.items():
        result[fid] = {
            "facility_id": status.facility_id,
            "tier": status.tier,
            "condition": status.condition,
            "efficiency_mult": round(status.efficiency_mult, 2),
            "branch_choice": status.branch_choice,
            "is_active": status.is_active,
            "breakdown_risk": round(status.breakdown_risk, 3),
            "upgrade_cost": get_facility_upgrade_cost(fid, status.tier),
        }
    return result
