"""设施侧「静默工作台」：区域资源活动挂载 + 按设施积存的挂机产出（须在设施面板领取）。

与 docs/sim_facility_tech_and_resource_gameplay.md §4 对齐：主动玩法可走既有 activity/run；
此处把入口收敛到地图上具体设施交互，并提供轻量积存（不改变既有 economy_tick 主账本逻辑）。
"""

from __future__ import annotations

from typing import Any

from .dispatch_system import get_facility_default

# 设施 id（大地图 FACILITIES / narrative_map）→ 可用资源活动 region_id（见 resource_activities）
FACILITY_ACTIVITY_REGIONS: dict[str, tuple[str, ...]] = {
    "mine": ("mine", "mine_deep"),
    "mine_ruins": ("mine_deep",),
    "lab": ("lab",),
    "comm": ("comm",),
    "defense": ("defense",),
    "listen": ("listen",),
    "shore_cave": ("coastal_cave",),
    "echo_site": ("echo_beacon",),
}

# 每推进 1 个基地日（仅静默期），向该设施积存池增加的「可领取」资源（不含即时 economy_tick）
FACILITY_IDLE_DAILY_ACCRUAL: dict[str, dict[str, int]] = {
    "mine": {"energy": 4},
    "mine_ruins": {"energy": 3},
    "lab": {"medical": 2},
    "comm": {"intel": 2},
    "defense": {"food": 3},
    "listen": {"intel": 1},
    "shore_cave": {"food": 2},
    "echo_site": {"intel": 2},
}


def merged_facility_row(sess: Any, facility_id: str) -> dict[str, Any]:
    base = get_facility_default(facility_id)
    row = {
        "tier": base.tier,
        "condition": base.condition,
        "efficiency_mult": base.efficiency_mult,
        "is_active": base.is_active,
    }
    row.update(sess.facility_status.get(facility_id) or {})
    return row


def accrue_facility_idle_stash(sess: Any) -> None:
    """在静默运营期内，对每个可用设施积存少量可领取产出。"""
    if str(getattr(sess, "story_phase", "") or "").strip() != "Sandbox":
        return
    bank: dict[str, dict[str, int]] = getattr(sess, "facility_idle_bank", None)
    if bank is None:
        bank = {}
        setattr(sess, "facility_idle_bank", bank)

    for fid, deltas in FACILITY_IDLE_DAILY_ACCRUAL.items():
        meta = merged_facility_row(sess, fid)
        if not meta.get("is_active", True):
            continue
        eff = float(meta.get("efficiency_mult", 1.0) or 1.0)
        cond_m = max(0.35, min(1.0, int(meta.get("condition", 100) or 100) / 100.0))
        tier_m = 1.0 + 0.08 * max(0, int(meta.get("tier", 1) or 1) - 1)
        stash = bank.setdefault(fid, {})
        for res_key, amt in deltas.items():
            add = int(max(0, round(int(amt) * eff * cond_m * tier_m)))
            if add <= 0:
                continue
            stash[res_key] = int(stash.get(res_key, 0)) + add


def compact_facility_idle_bank_preview(bank: Any) -> dict[str, dict[str, int]]:
    if not isinstance(bank, dict):
        return {}
    out: dict[str, dict[str, int]] = {}
    for fid, stash in bank.items():
        if not stash or not isinstance(stash, dict):
            continue
        pos = {k: int(v) for k, v in stash.items() if int(v) > 0}
        if pos:
            out[str(fid)] = pos
    return out


def claim_facility_idle(sess: Any, facility_id: str) -> tuple[bool, str | None, dict[str, int]]:
    """将领取池并入玩家资源，清零该设施积存。"""
    if str(getattr(sess, "story_phase", "") or "").strip() != "Sandbox":
        return False, "仅在静默运营期可在设施工作台领取积存产出。", {}

    fid = str(facility_id or "").strip()
    if not fid:
        return False, "缺少 facility_id。", {}

    bank_raw = getattr(sess, "facility_idle_bank", None) or {}
    bank: dict[str, dict[str, int]] = bank_raw if isinstance(bank_raw, dict) else {}

    stash = dict(bank.get(fid, {}) or {})
    payout: dict[str, int] = {}
    for k, v in stash.items():
        n = int(v)
        if n > 0:
            payout[str(k)] = n

    if not payout:
        return False, "当前没有可领取的积存产出（需先推进基地日累积）。", {}

    sess.resources.apply(**payout)
    bank[fid] = {}
    setattr(sess, "facility_idle_bank", bank)
    return True, None, payout


def facility_sim_overlays_snapshot(sess: Any) -> dict[str, Any]:
    """供 GET /api/state：各「工作台设施」快照，避免只靠 POST /facility/check 时易被旧网关/错位进程截断字段。"""
    return {fid: build_facility_sim_overlay(sess, fid) for fid in FACILITY_ACTIVITY_REGIONS}


def build_facility_sim_overlay(sess: Any, facility_id: str) -> dict[str, Any]:
    """供 POST /api/facility/check 返回：是否在静默期内展示工作台与活动列表。"""
    fid = str(facility_id or "").strip()
    regions = FACILITY_ACTIVITY_REGIONS.get(fid)
    if not regions:
        return {"enabled": False, "facility_id": fid, "workbench_supported": False}

    sandbox = str(getattr(sess, "story_phase", "") or "").strip() == "Sandbox"

    idle_bank = getattr(sess, "facility_idle_bank", None) or {}
    stash_preview: dict[str, int] = {}
    raw_stash = {}
    if isinstance(idle_bank, dict):
        raw_stash = idle_bank.get(fid, {}) or {}
    if isinstance(raw_stash, dict):
        stash_preview = {k: int(v) for k, v in raw_stash.items() if int(v or 0) > 0}

    if not sandbox:
        sp = str(getattr(sess, "story_phase", "") or "").strip() or "StoryBeat"
        return {
            "enabled": False,
            "workbench_supported": True,
            "facility_id": fid,
            "story_phase": sp,
            "inactive_reason_zh": (
                f"设施工作台仅在「静默运营」期开放（当前节拍：{sp}）。先在侧栏进入静默后再来此处，可进行「手动校准作业」或在面板领取挂机积存。"
            ),
        }

    from .resource_activities import build_activity_catalog_for_session

    reg_set = frozenset(regions)
    full = build_activity_catalog_for_session(sess)
    acts = [a for a in full if str(a.get("region_id") or "") in reg_set]

    primary_resource_hint = ""
    if acts:
        pr = str(acts[0].get("primary_resource") or "")
        lut = {"energy": "能源", "food": "补给", "medical": "医疗", "intel": "情报"}
        primary_resource_zh = lut.get(pr, pr)
        primary_resource_hint = (
            f"本设施工作台可调度与「{primary_resource_zh}」相关的区域作业；成功后资源即时入账。"
        )

    idle_hint_zh = ""
    if stash_preview:
        parts = []
        lk = {"energy": "能源", "food": "补给", "medical": "医疗", "intel": "情报"}
        for rk, rv in sorted(stash_preview.items()):
            parts.append(f"{lk.get(rk, rk)} +{rv}")
        idle_hint_zh = "积存可领取：" + "、".join(parts)
    else:
        idle_hint_zh = (
            "挂机积存：随「基地日推进」在每个静默日少量累积；请到本面板领取入账（不占用手动玩法冷却）。"
        )

    return {
        "enabled": True,
        "workbench_supported": True,
        "story_phase": "Sandbox",
        "facility_id": fid,
        "activity_regions": list(regions),
        "activities": acts,
        "idle_claimable": stash_preview,
        "idle_claimable_zh": idle_hint_zh,
        "manual_hint_zh": primary_resource_hint
        or "选择一项区域作业并完成校准后提交；成功与否仍按活动自带风险判定。",
    }
