"""野外远征（静默期占位）：出发前消耗、归国日结算、与 explorer_access 门禁联动。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from .explorer_access import zone_is_unlocked

@dataclass(frozen=True)
class ExpeditionDestSpec:
    id: str
    label_zh: str
    zone_gate_id: str
    duration_days: int
    cost_energy: int
    cost_food: int
    payout_intel: int
    payout_energy: int
    bulletin_arrival_zh: str


DESTINATIONS: tuple[ExpeditionDestSpec, ...] = (
    ExpeditionDestSpec(
        id="coastal_scout",
        label_zh="海岸线侦察（洞穴潮位窗口）",
        zone_gate_id="coastal_cave",
        duration_days=2,
        cost_energy=6,
        cost_food=8,
        payout_intel=4,
        payout_energy=0,
        bulletin_arrival_zh="侦察队归国：潮汐窗口地形已标定，获得情报汇总。",
    ),
    ExpeditionDestSpec(
        id="mine_deep_run",
        label_zh="深层矿脉应急巡察",
        zone_gate_id="mine_deep",
        duration_days=3,
        cost_energy=10,
        cost_food=10,
        payout_intel=2,
        payout_energy=22,
        bulletin_arrival_zh="矿区巡察归来：高风险换得一批可分配能源配额。",
    ),
    ExpeditionDestSpec(
        id="echo_pickup",
        label_zh="信标塔外围信道嗅探",
        zone_gate_id="echo_beacon",
        duration_days=2,
        cost_energy=12,
        cost_food=6,
        payout_intel=8,
        payout_energy=-5,
        bulletin_arrival_zh="小队携截获频段样本返回；回声特征已入库。",
    ),
    ExpeditionDestSpec(
        id="parliament_scrub",
        label_zh="议会废墟残骸回收",
        zone_gate_id="parliament_outpost",
        duration_days=3,
        cost_energy=8,
        cost_food=12,
        payout_intel=10,
        payout_energy=0,
        bulletin_arrival_zh="前哨残骸扫描完成：获得议会链路残留条目。",
    ),
)

ALLOWED_LEADERS = frozenset({"chubby", "karen", "jin"})

LEADER_LABEL_ZH = {"chubby": "小胖", "karen": "卡伦", "jin": "堇"}

_DEST_MAP: dict[str, ExpeditionDestSpec] = {d.id: d for d in DESTINATIONS}


def expedition_catalog_payload(sess: object) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in DESTINATIONS:
        ok = zone_is_unlocked(sess, d.zone_gate_id)
        out.append(
            {
                "dest_id": d.id,
                "label_zh": d.label_zh,
                "duration_days": d.duration_days,
                "reward_hint_zh": f"归国约可得：情报 +{d.payout_intel}，能源 {d.payout_energy:+d}",
                "cost": {"energy": d.cost_energy, "food": d.cost_food},
                "zone_gate_id": d.zone_gate_id,
                "unlocked": ok,
                "blocked_reason_zh": "" if ok else "目标区域门禁未满足（见大地图禁区提示）。",
            }
        )
    return out


def expeditions_active_ui_payload(sess: object) -> list[dict[str, Any]]:
    """
    静默 HUD 专用：在原 active 条目上增补中文目标名、归国倒计时与进度占比。
    """

    wd = int(getattr(sess, "world_day", 1) or 1)
    out: list[dict[str, Any]] = []
    for raw in getattr(sess, "expeditions_active", ()) or ():
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        if str(row.get("status") or "") != "active":
            continue
        dest = _DEST_MAP.get(str(row.get("destination_id") or ""))
        leader = str(row.get("leader_npc_id") or "").strip()
        ret = int(row.get("return_world_day") or 0)
        depart = int(row.get("depart_world_day") or wd)
        duration = int(dest.duration_days) if dest else max(1, ret - depart)
        days_until_return = max(0, ret - wd)
        elapsed = max(0, wd - depart)
        progress = max(0.0, min(1.0, float(elapsed) / float(duration))) if duration > 0 else 0.0
        row["destination_label_zh"] = dest.label_zh if dest else str(row.get("destination_id") or "")
        row["leader_label_zh"] = LEADER_LABEL_ZH.get(leader, leader)
        row["duration_days"] = duration
        row["days_until_return"] = days_until_return
        row["progress"] = round(progress, 3)
        out.append(row)
    return out


def _active_leader_ids(sess: object) -> frozenset[str]:
    ex = getattr(sess, "expeditions_active", ()) or ()
    leaders = []
    for row in ex:
        lid = str((row or {}).get("leader_npc_id") or "").strip()
        if lid:
            leaders.append(lid)
    return frozenset(leaders)


def start_expedition(sess: object, leader_npc_id: str, destination_id: str) -> tuple[bool, str | None, dict[str, Any] | None]:
    phase = str(getattr(sess, "story_phase", "StoryBeat") or "").strip()
    if phase != "Sandbox":
        return False, "仅在静默运营期内可签发野外远征。", None

    leader = (leader_npc_id or "").strip()
    if leader not in ALLOWED_LEADERS:
        return False, "小队长必须为：chubby（小胖）、karen（卡伦）、jin（堇）三者之一。", None

    if leader in _active_leader_ids(sess):
        return False, "该干员尚有未归建的远征。", None

    dest = _DEST_MAP.get((destination_id or "").strip())
    if not dest:
        return False, "未知的远征目标。", None

    if not zone_is_unlocked(sess, dest.zone_gate_id):
        return False, "该区域尚未满足派出条件（门禁未开）。", None

    wd = int(getattr(sess, "world_day", 1) or 1)

    res = sess.resources
    if res.energy < dest.cost_energy or res.food < dest.cost_food:
        return False, "出发前物资不足以支付本条远征的基础消耗。", None

    res.apply(energy=-dest.cost_energy, food=-dest.cost_food)

    eid = f"exp_{uuid.uuid4().hex[:12]}"
    row = {
        "id": eid,
        "leader_npc_id": leader,
        "destination_id": dest.id,
        "depart_world_day": wd,
        "return_world_day": wd + int(dest.duration_days),
        "status": "active",
        "bulletin_zh": dest.bulletin_arrival_zh,
    }
    lst: list[Any] = list(getattr(sess, "expeditions_active") or [])
    lst.append(row)
    setattr(sess, "expeditions_active", lst)

    from .sim_sandbox import append_bulletin_zh

    append_bulletin_zh(
        sess,
        f"远征出发：{LEADER_LABEL_ZH.get(leader, leader)} → {dest.label_zh}，预计第 {row['return_world_day']} 日归国。",
    )
    return True, None, row


def settle_expedition_arrivals(sess: object) -> list[dict[str, Any]]:
    """在新世界日当天结算所有到期远征（应在 world_day 递增至目标值之后调用）。"""
    wd = int(getattr(sess, "world_day", 1) or 1)
    lst = list(getattr(sess, "expeditions_active") or [])
    if not lst:
        return []

    from .sim_sandbox import append_bulletin_zh

    remain: list[dict[str, Any]] = []
    settled: list[dict[str, Any]] = []

    for row in lst:
        if str(row.get("status") or "") != "active":
            continue
        ret_day = int(row.get("return_world_day") or 0)
        if wd < ret_day:
            remain.append(row)
            continue

        dest = _DEST_MAP.get(str(row.get("destination_id") or ""))
        if not dest:
            remain.append(row)
            continue

        sess.resources.apply(energy=dest.payout_energy, intel=dest.payout_intel)
        bulletin = row.get("bulletin_zh") or dest.bulletin_arrival_zh
        append_bulletin_zh(sess, str(bulletin))
        settled.append(
            {
                "id": row.get("id"),
                "leader_npc_id": row.get("leader_npc_id"),
                "destination_id": dest.id,
                "return_world_day": ret_day,
            }
        )

    setattr(sess, "expeditions_active", remain)
    return settled
