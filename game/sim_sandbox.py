"""静默运营期（Sandbox）策略、简报与日度经济 tick。

设计对齐 docs/sim_*.md；与叙事相位字段同存于 GameSession。
"""

from __future__ import annotations


# narrative-sandbox-policy: allow 立即结算；queue 进入待办队列，退出 Sandbox 时再结算；block_ui 仅拒绝
SANDBOX_POLICY: dict[str, str] = {
    "mine_deepen": "allow",
    "mine_limit": "allow",
    "defense_fortify": "allow",
    "supply_medical_first": "allow",
    "comm_array_encrypt": "queue",
    "comm_array_broadcast": "queue",
    "lab_neural_scan": "queue",
    "lab_sync_suppressor": "queue",
    "listen_station_on": "queue",
    "reject_echo_aid": "queue",
    "accept_echo_aid": "queue",
    "purge_partial_mine": "queue",
}


def sandbox_policy(tag: str) -> str:
    return SANDBOX_POLICY.get(tag.strip(), "queue")


SANDBOX_NPC_CALLS_SOFT_CAP_DAY = 5
_MAX_BULLETINS = 48


def append_bulletin_zh(sess: object, line: str) -> None:
    lst: list[str] = getattr(sess, "sandbox_bulletin_zh", [])
    text = line.strip()
    if not text:
        return
    lst.append(text)
    overflow = len(lst) - _MAX_BULLETINS
    if overflow > 0:
        del lst[0:overflow]


def sandbox_days_elapsed(sess: object) -> int:
    wd = int(getattr(sess, "world_day", 1) or 1)
    ent = getattr(sess, "sandbox_enter_world_day", None)
    if ent is None:
        return 0
    return max(0, wd - int(ent))


def sandbox_min_remaining_days(sess: object) -> int | None:
    """距最短静默还差几天；若无下限则返回 None。"""
    m = getattr(sess, "sandbox_min_world_days", None)
    if m is None:
        return None
    need = max(0, int(m))
    return max(0, need - sandbox_days_elapsed(sess))


def can_exit_sandbox(sess: object, *, force: bool = False) -> tuple[bool, str | None]:
    if getattr(sess, "story_phase", "StoryBeat") != "Sandbox":
        return False, "当前并非静默运营期。"
    if force:
        return True, None
    rem = sandbox_min_remaining_days(sess)
    if rem is not None and rem > 0:
        return False, f"最短静默期未满：仍需运营至少 {rem} 个基地日。"
    return True, None


def economy_tick_world_day(sess: object) -> dict[str, object]:
    """推进一个『基地日』：日常消耗 / 岸线蠕变 / 被动产出；不写主线账本。"""
    bullets: list[str] = []

    res = sess.resources  # BaseResources
    hv = sess.hidden

    # 日常 upkeep
    res.apply(energy=-4, food=-3)

    # 源矿 passive（轻量占位：与经营管理标签弱联动）
    energy_gain = 10
    applied: list[str] = list(getattr(sess, "applied_management_tags", []) or ())
    appl = frozenset(applied)
    if "mine_deepen" in appl:
        energy_gain += 8
    if "mine_limit" in appl:
        energy_gain -= 6
        bullets.append("限制开采模式下，矿区日产量明显下降。")

    # 委任系统效果
    dispatcher = getattr(sess, "dispatched_npc", None)
    if dispatcher:
        from .dispatch_system import DISPATCH_NPC_INFO

        info = DISPATCH_NPC_INFO.get(dispatcher, {})
        modifiers = info.get("effect_modifiers", {})
        if modifiers.get("mine_deepen_likelihood", 0) > 0.5:
            energy_gain += 4
            bullets.append(f"{info.get('label_zh', dispatcher)}正在执行积极开采策略。")
        elif modifiers.get("mine_limit_likelihood", 0) > 0.5:
            energy_gain -= 3
            bullets.append(f"{info.get('label_zh', dispatcher)}优先保障基地安全。")

    # 士气系统效果
    morale = int(getattr(sess, "morale", 75))
    if morale < 40:
        energy_gain = int(energy_gain * 0.8)
        bullets.append("士气低迷导致产出效率下降。")
    elif morale > 80:
        energy_gain = int(energy_gain * 1.1)
        bullets.append("高士气提振了基地效率。")

    income = max(int(energy_gain), 0)
    before_e = res.energy
    res.apply(energy=income)

    gain_e = max(0, res.energy - before_e)

    inc_delta = 0.45
    if "mine_deepen" in appl:
        inc_delta += 0.28
    if "mine_limit" in appl:
        inc_delta -= 0.12
    if "defense_fortify" in appl:
        inc_delta -= 0.38
    if "purge_partial_mine" in appl:
        inc_delta -= 0.25

    before_inc = float(hv.INCURSION)
    hv.apply_delta("INCURSION", inc_delta)

    # 士气系统：食物短缺降低士气
    if res.food < 20:
        sess.morale = max(0, sess.morale - 3)
        bullets.append("食物短缺，士气下降。")
    elif res.food > 50:
        sess.morale = min(100, sess.morale + 1)

    # 设施状态影响
    facility_status = getattr(sess, "facility_status", {})
    mine_status = facility_status.get("mine", {})
    mine_efficiency = mine_status.get("efficiency_mult", 1.0)
    if mine_efficiency < 0.8:
        actual_gain = int(gain_e * mine_efficiency)
        bullets.append(f"源矿机工况不佳（{int(mine_efficiency * 100)}%），实际能源产出 {actual_gain}。")
        gain_e = actual_gain

    bullets.append(
        f"基地日结转：物资消耗已记账；矿区净能源约 +{gain_e}。"
        f"岸线压力变化 {before_inc:.1f}→{hv.INCURSION:.1f}。"
    )

    from .facility_sim_ops import accrue_facility_idle_stash

    accrue_facility_idle_stash(sess)

    from .underground_workshop import workshop_daily_pass

    workshop_daily_pass(sess)

    setattr(sess, "sandbox_npc_calls_this_day", 0)

    summary = "; ".join([b for b in bullets if b])
    append_bulletin_zh(sess, f"—— 第 {getattr(sess, 'world_day', 1)} 日 —— {summary}")

    return {
        "world_day_before": getattr(sess, "world_day", 1),
        "energy_daily_gain_approx": gain_e,
        "incursion_delta_approx": round(inc_delta, 3),
        "morale": sess.morale,
        "bulletin_line_zh": summary,
    }


def next_world_day(sess: object) -> dict[str, object]:
    """world_day+=1；先做远征归国，再Economy Tick；返回明细。"""
    wd = int(getattr(sess, "world_day", 1) or 1)
    setattr(sess, "world_day", wd + 1)

    from .expeditions import settle_expedition_arrivals
    from .world_clock import reset_clock_morning

    reset_clock_morning(sess, hour=8, minute=0)

    ex_settled = settle_expedition_arrivals(sess)
    eco = economy_tick_world_day(sess)

    # 自动休整到期恢复主线（静默过渡，不额外广播）
    auto_resume = bool(getattr(sess, "sandbox_auto_resume", False))
    if auto_resume:
        resume_day = getattr(sess, "sandbox_auto_resume_day", None)
        if resume_day is not None and int(getattr(sess, "world_day", 1)) >= int(resume_day):
            from .bridge import flush_management_queue

            drained, _ = flush_management_queue(sess)
            sess.story_phase = "StoryBeat"
            sess.sandbox_enter_world_day = None
            sess.sandbox_min_world_days = None
            sess.sandbox_auto_resume = False
            sess.sandbox_auto_resume_day = None
            if drained:
                append_bulletin_zh(sess, f"基地运营调整：决算队列落地 {len(drained)} 项。")
            # 不额外播报"恢复主线"，让玩家自然发现剧情已可用

    return {"world_day_after": sess.world_day, "expeditions_settled": ex_settled, "economy_tick": eco}
