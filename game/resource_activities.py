"""四类资源「地图主动玩法」系统：对齐 docs/sim_facility_tech_and_resource_gameplay.md §4。

每种资源绑定一类区域玩法，玩家在地图上进行短时操作换取资源。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceActivity:
    """单个资源活动的规格。"""

    activity_id: str
    region_id: str  # 与 map_design.md zone slug 对齐
    primary_resource: str  # "energy" | "food" | "medical" | "intel"
    run_kind_zh: str  # 玩法中文名称
    cooldown_world_days: int  # 冷却天数
    payout_bundle_id: str  # 奖励包ID
    incursion_notes: str = ""  # 岸线影响说明
    sandbox_eligible: bool = True
    # 奖励数值（可扩展为更复杂的奖励表）
    reward_energy: int = 0
    reward_food: int = 0
    reward_medical: int = 0
    reward_intel: int = 0
    # 消耗
    cost_energy: int = 0
    cost_food: int = 0
    # 风险
    risk_failure: float = 0.0  # 失败概率 0-1
    risk_reward_mult: float = 1.0  # 成功时奖励倍数


# 能源类活动：源矿开采
ENERGY_ACTIVITIES: list[ResourceActivity] = [
    ResourceActivity(
        activity_id="mine_standard_run",
        region_id="mine",
        primary_resource="energy",
        run_kind_zh="标准开采作业",
        cooldown_world_days=1,
        payout_bundle_id="energy_standard",
        incursion_notes="开采作业可能加速岸线侵入",
        sandbox_eligible=True,
        reward_energy=15,
        cost_energy=2,
        risk_failure=0.05,
    ),
    ResourceActivity(
        activity_id="mine_deep_extraction",
        region_id="mine_deep",
        primary_resource="energy",
        run_kind_zh="深层矿脉抽取",
        cooldown_world_days=2,
        payout_bundle_id="energy_deep",
        incursion_notes="深层开采大幅加速岸线侵入",
        sandbox_eligible=True,
        reward_energy=35,
        cost_energy=8,
        risk_failure=0.15,
        risk_reward_mult=1.3,
    ),
]

# 食物类活动：海岸防线后勤
FOOD_ACTIVITIES: list[ResourceActivity] = [
    ResourceActivity(
        activity_id="coastal_forage",
        region_id="coastal_cave",
        primary_resource="food",
        run_kind_zh="潮汐采集",
        cooldown_world_days=1,
        payout_bundle_id="food_coastal",
        incursion_notes="需在潮汐窗口完成",
        sandbox_eligible=True,
        reward_food=12,
        cost_energy=3,
        risk_failure=0.10,
    ),
    ResourceActivity(
        activity_id="defense_patrol",
        region_id="defense",
        primary_resource="food",
        run_kind_zh="防线巡逻采集",
        cooldown_world_days=1,
        payout_bundle_id="food_patrol",
        incursion_notes="巡逻可顺便收集物资",
        sandbox_eligible=True,
        reward_food=8,
        reward_intel=2,
        risk_failure=0.08,
    ),
]

# 医疗类活动：实验室操作
MEDICAL_ACTIVITIES: list[ResourceActivity] = [
    ResourceActivity(
        activity_id="lab_triage",
        region_id="lab",
        primary_resource="medical",
        run_kind_zh="伤员分拣与配给",
        cooldown_world_days=1,
        payout_bundle_id="medical_lab",
        incursion_notes="处置效率影响救治质量",
        sandbox_eligible=True,
        reward_medical=10,
        cost_energy=4,
        cost_food=2,
        risk_failure=0.12,
    ),
    ResourceActivity(
        activity_id="lab_drug_synth",
        region_id="lab",
        primary_resource="medical",
        run_kind_zh="简易药剂合成",
        cooldown_world_days=2,
        payout_bundle_id="medical_synth",
        incursion_notes="消耗原材料合成医疗物资",
        sandbox_eligible=True,
        reward_medical=18,
        cost_energy=6,
        risk_failure=0.08,
    ),
]

# 情报类活动：通讯阵列/回声塔
INTEL_ACTIVITIES: list[ResourceActivity] = [
    ResourceActivity(
        activity_id="comm_signal_scan",
        region_id="comm",
        primary_resource="intel",
        run_kind_zh="频段扫描与解谜",
        cooldown_world_days=1,
        payout_bundle_id="intel_comm",
        incursion_notes="解谜需要专注与时间",
        sandbox_eligible=True,
        reward_intel=8,
        cost_energy=3,
        risk_failure=0.15,
    ),
    ResourceActivity(
        activity_id="echo_sniff",
        region_id="echo_beacon",
        primary_resource="intel",
        run_kind_zh="回声塔信道嗅探",
        cooldown_world_days=2,
        payout_bundle_id="intel_echo",
        incursion_notes="接触回声集团频段，有风险",
        sandbox_eligible=True,
        reward_intel=15,
        reward_energy=-5,  # 可能消耗能源
        risk_failure=0.20,
    ),
    ResourceActivity(
        activity_id="listen_fragment",
        region_id="listen",
        primary_resource="intel",
        run_kind_zh="源语片段重组",
        cooldown_world_days=2,
        payout_bundle_id="intel_source",
        incursion_notes="整理源的低语碎片",
        sandbox_eligible=True,
        reward_intel=12,
        reward_energy=5,  # 源的微弱回馈
        risk_failure=0.10,
    ),
]

# 合并所有活动
ALL_ACTIVITIES: list[ResourceActivity] = (
    ENERGY_ACTIVITIES
    + FOOD_ACTIVITIES
    + MEDICAL_ACTIVITIES
    + INTEL_ACTIVITIES
)

# 活动 `region_id`（语义片区）→ `explorer_access` 中门禁 zone id。
# 未列出的片区视为基地常驻区域，静默内默认可进行操作（不须额外门禁表项）。
_ACTIVITY_REGION_TO_EXPLORER_GATE: dict[str, str] = {
    "mine_deep": "mine_deep",
    "coastal_cave": "coastal_cave",
    "echo_beacon": "echo_beacon",
    "listen": "listen_station_vault",
}


# 按ID索引
_ACTIVITY_MAP: dict[str, ResourceActivity] = {a.activity_id: a for a in ALL_ACTIVITIES}

# 按资源类型索引
ACTIVITIES_BY_RESOURCE: dict[str, list[ResourceActivity]] = {
    "energy": ENERGY_ACTIVITIES,
    "food": FOOD_ACTIVITIES,
    "medical": MEDICAL_ACTIVITIES,
    "intel": INTEL_ACTIVITIES,
}


def get_activity(activity_id: str) -> ResourceActivity | None:
    """通过ID获取活动。"""
    return _ACTIVITY_MAP.get(activity_id)


def get_activities_for_region(region_id: str) -> list[ResourceActivity]:
    """获取指定区域的所有可用活动。"""
    return [a for a in ALL_ACTIVITIES if a.region_id == region_id]


def get_activities_by_resource(resource: str) -> list[ResourceActivity]:
    """获取指定资源类型的所有活动。"""
    return ACTIVITIES_BY_RESOURCE.get(resource, [])


def can_run_activity(
    activity_id: str,
    current_world_day: int,
    cooldowns: dict[str, int],
) -> tuple[bool, str]:
    """检查活动是否可以执行。"""
    activity = get_activity(activity_id)
    if not activity:
        return False, f"未知的活动ID: {activity_id}"

    last_day = cooldowns.get(activity_id, 0)
    days_since = current_world_day - last_day

    if days_since < activity.cooldown_world_days:
        remaining = activity.cooldown_world_days - days_since
        return False, f"活动冷却中，还需等待 {remaining} 天"

    return True, ""


def simulate_activity_outcome(
    activity: ResourceActivity,
    success: bool,
) -> dict[str, int]:
    """模拟活动结果。"""
    if not success:
        # 成本已在服务端先行扣除；此处不再二次扣资源，简报仅叙事向说明即可。
        return {}

    mult = activity.risk_reward_mult if success else 1.0
    rewards = {
        "energy": int(activity.reward_energy * mult),
        "food": int(activity.reward_food * mult),
        "medical": int(activity.reward_medical * mult),
        "intel": int(activity.reward_intel * mult),
    }
    return {k: v for k, v in rewards.items() if v != 0}


def activity_explorer_gate_ok(sess: Any, activity: ResourceActivity) -> tuple[bool, str]:
    gate = _ACTIVITY_REGION_TO_EXPLORER_GATE.get(activity.region_id)
    if not gate:
        return True, ""
    from .explorer_access import zone_blocked_reason_zh, zone_is_unlocked

    if zone_is_unlocked(sess, gate):
        return True, ""
    reason = zone_blocked_reason_zh(sess, gate)
    return False, reason or "目标区域门禁未开放。"


def build_activity_catalog_for_session(sess: Any) -> list[dict[str, Any]]:
    """供 GET /api/state 静默块：每项含门禁与冷却实况。"""
    cds: dict[str, int] = dict(getattr(sess, "activity_cooldowns", {}) or {})
    wd = int(getattr(sess, "world_day", 1) or 1)
    res = getattr(sess, "resources", None)

    rows: list[dict[str, Any]] = []
    for a in ALL_ACTIVITIES:
        if not a.sandbox_eligible:
            continue

        gate_ok, gate_zh = activity_explorer_gate_ok(sess, a)
        last_day = int(cds.get(a.activity_id, 0))
        days_since = wd - last_day
        cooldown_ok = days_since >= int(a.cooldown_world_days)
        remain_cd = max(0, int(a.cooldown_world_days) - days_since) if not cooldown_ok else 0
        affordable = bool(res) and res.energy >= a.cost_energy and res.food >= a.cost_food

        br: list[str] = []
        if not gate_ok:
            br.append(gate_zh)
        elif not cooldown_ok:
            br.append(f"冷却中：尚需约 {remain_cd} 基地日后再试")
        elif not affordable:
            br.append("行前物资不足以支付消耗")

        rows.append(
            {
                "activity_id": a.activity_id,
                "region_id": a.region_id,
                "primary_resource": a.primary_resource,
                "run_kind_zh": a.run_kind_zh,
                "cooldown_world_days": a.cooldown_world_days,
                "reward_preview": {
                    "energy": a.reward_energy,
                    "food": a.reward_food,
                    "medical": a.reward_medical,
                    "intel": a.reward_intel,
                },
                "cost_preview": {
                    "energy": a.cost_energy,
                    "food": a.cost_food,
                },
                "incursion_notes": a.incursion_notes,
                "risk_failure": a.risk_failure,
                "zone_unlocked": gate_ok,
                "blocked_gate_zh": "" if gate_ok else gate_zh,
                "cooldown_remain_days": remain_cd,
                "can_run_now": gate_ok and cooldown_ok and affordable,
                "blocked_reason_zh": "".join(br),
            }
        )
    return rows


def build_activity_catalog_payload(
    region_id: str | None = None,
    sandbox_eligible_only: bool = True,
) -> list[dict[str, Any]]:
    """构建活动目录payload供前端使用。"""
    activities = ALL_ACTIVITIES
    if region_id:
        activities = get_activities_for_region(region_id)
    if sandbox_eligible_only:
        activities = [a for a in activities if a.sandbox_eligible]

    return [
        {
            "activity_id": a.activity_id,
            "region_id": a.region_id,
            "primary_resource": a.primary_resource,
            "run_kind_zh": a.run_kind_zh,
            "cooldown_world_days": a.cooldown_world_days,
            "reward_preview": {
                "energy": a.reward_energy,
                "food": a.reward_food,
                "medical": a.reward_medical,
                "intel": a.reward_intel,
            },
            "cost_preview": {
                "energy": a.cost_energy,
                "food": a.cost_food,
            },
            "incursion_notes": a.incursion_notes,
            "risk_failure": a.risk_failure,
            "sandbox_eligible": a.sandbox_eligible,
        }
        for a in activities
    ]


def build_region_activity_summary(
    region_id: str,
    cooldowns: dict[str, int],
    current_world_day: int,
) -> dict[str, Any]:
    """构建单个区域的资源活动汇总。"""
    activities = get_activities_for_region(region_id)
    available = []
    on_cooldown = []

    for a in activities:
        can_run, reason = can_run_activity(a.activity_id, current_world_day, cooldowns)
        entry = {
            "activity_id": a.activity_id,
            "run_kind_zh": a.run_kind_zh,
            "primary_resource": a.primary_resource,
            "cooldown_remaining": max(
                0, a.cooldown_world_days - (current_world_day - cooldowns.get(a.activity_id, 0))
            ),
        }
        if can_run:
            available.append(entry)
        else:
            entry["blocked_reason_zh"] = reason
            on_cooldown.append(entry)

    return {
        "region_id": region_id,
        "available_activities": available,
        "cooldown_activities": on_cooldown,
    }
