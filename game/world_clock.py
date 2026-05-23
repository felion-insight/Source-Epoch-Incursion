"""游戏内时钟与世界地图一次性交互（购灯等）。"""

from __future__ import annotations

DAY_MINUTES = 24 * 60


def clock_display_parts(sess: object) -> dict[str, int | str]:
    m = int(getattr(sess, "world_minute_of_day", 8 * 60) or 0)
    m = max(0, min(DAY_MINUTES - 1, m))
    hh = m // 60
    mm = m % 60
    return {
        "minute_of_day": m,
        "hour": hh,
        "minute": mm,
        "display_zh": f"{hh:02d}:{mm:02d}",
    }


def advance_world_minutes(sess: object, delta: int) -> dict[str, int | str]:
    """在同一基地日内推进若干分钟，跨午夜则环绕。"""
    cur = int(getattr(sess, "world_minute_of_day", 8 * 60) or 0)
    cur = (cur + int(delta)) % DAY_MINUTES
    setattr(sess, "world_minute_of_day", cur)
    return clock_display_parts(sess)


def reset_clock_morning(sess: object, *, hour: int = 8, minute: int = 0) -> None:
    h = max(0, min(23, int(hour)))
    mi = max(0, min(59, int(minute)))
    setattr(sess, "world_minute_of_day", h * 60 + mi)


def try_purchase_industrial_floodlight(sess: object) -> tuple[bool, str | None]:
    """docs/map_design.md：深层能力锁 — 约 500 资源购探照灯；此处用 500 能源结算。"""
    plot = getattr(sess, "plot", None)
    res = getattr(sess, "resources", None)
    if plot is None or res is None:
        return False, "会话状态异常。"

    if plot.has("floodlight_equipped") or plot.has("mine_deep_lit"):
        return False, "深矿区已可通行（已购灯或已通过经营/剧情解锁照明）。"

    if int(res.energy) < 500:
        return False, "购置工业探照灯需消耗 500 能源。"

    res.apply(energy=-500)
    plot.enable("floodlight_equipped")
    from .sim_sandbox import append_bulletin_zh

    append_bulletin_zh(sess, "已调配工业探照灯与支护套件：废弃矿场深层现可安全进入。")
    return True, None
