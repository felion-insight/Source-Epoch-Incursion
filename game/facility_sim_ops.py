"""设施侧「静默工作台」：按设施积存的挂机产出（须在设施面板领取）。

与 docs/sim_facility_tech_and_resource_gameplay.md §4 对齐：提供轻量积存（不改变既有 economy_tick 主账本逻辑）。
"""

from __future__ import annotations

from typing import Any

from .dispatch_system import get_facility_default

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
    return {fid: build_facility_sim_overlay(sess, fid) for fid in FACILITY_IDLE_DAILY_ACCRUAL}


def build_facility_sim_overlay(sess: Any, facility_id: str) -> dict[str, Any]:
    """供 POST /api/facility/check 返回：是否在静默期内展示工作台与挂机积存。"""
    fid = str(facility_id or "").strip()
    if fid not in FACILITY_IDLE_DAILY_ACCRUAL:
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
                f"设施工作台仅在「静默运营」期开放（当前节拍：{sp}）。先在侧栏进入静默后再来此处领取挂机积存。"
            ),
        }

    idle_hint_zh = ""
    if stash_preview:
        parts = []
        lk = {"energy": "能源", "food": "补给", "medical": "医疗", "intel": "情报"}
        for rk, rv in sorted(stash_preview.items()):
            parts.append(f"{lk.get(rk, rk)} +{rv}")
        idle_hint_zh = "积存可领取：" + "、".join(parts)
    else:
        idle_hint_zh = (
            "挂机积存：随「基地日推进」在每个静默日少量累积；请到本面板领取入账。"
        )

    return {
        "enabled": True,
        "workbench_supported": True,
        "story_phase": "Sandbox",
        "facility_id": fid,
        "idle_claimable": stash_preview,
        "idle_claimable_zh": idle_hint_zh,
    }
