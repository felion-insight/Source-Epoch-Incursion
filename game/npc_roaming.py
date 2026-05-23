"""与 docs/NPC_movement.md 对齐的 NPC 游荡摘要（由会话时钟驱动，供 API 与 UI 文案）。"""

from __future__ import annotations

LOC_LABEL_ZH: dict[str, str] = {
    "base_core": "基地核心",
    "coast_defense": "海岸防线",
    "comm_array": "通讯阵列",
    "med_lab": "医疗实验室",
    "source_mine": "源矿采集点",
    "mine_surface": "废弃矿场 · 表层",
    "listen_station": "地下监听站",
    "coastal_cave": "海岸线洞穴",
    "purify_grove": "净空会圣树",
    "sunk_lab": "沉没实验室",
    "underground_lab": "地下实验室（隐蔽）",
    "echo_spectral": "电子界面（回声-7）",
}


def _hour(sess: object) -> int:
    m = int(getattr(sess, "world_minute_of_day", 8 * 60) or 0)
    return (m // 60) % 24


def _done(sess: object, node_id: str) -> bool:
    return node_id in (getattr(sess, "completed_nodes", None) or ())


def _plot(sess: object, name: str) -> bool:
    plot = getattr(sess, "plot", None)
    if plot is None:
        return False
    return bool(plot.has(name))


def _focus(sess: object) -> set[str]:
    try:
        cur = sess.current_node()
        return set(cur.npc_focus or ())
    except Exception:
        return set()


def _stable_pick(seed: int, choices: tuple[str, ...]) -> str:
    return choices[seed % len(choices)] if choices else "base_core"


def _hash_seed(npc_id: str, key: int) -> int:
    s = f"{npc_id}:{key}"
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def npc_roaming_slug(sess: object, npc_id: str, *, hour: int | None = None) -> str:
    """返回内部 slug（与 LOC_LABEL_ZH 键一致）。"""
    h = hour if hour is not None else _hour(sess)
    focus = _focus(sess)
    if npc_id in focus:
        return "base_core"

    inc = float(getattr(getattr(sess, "hidden", object), "INCURSION", 25))

    if npc_id == "karen":
        if inc >= 55:
            return "coast_defense"
        if h >= 20 or h < 8:
            return "coast_defense"
        return "comm_array" if (h // 2) % 2 else "base_core"

    if npc_id == "dr_lin":
        if h >= 22 or h < 8:
            return "med_lab"
        if 18 <= h < 22:
            return "listen_station" if _plot(sess, "listen_station_built") else "med_lab"
        if 12 <= h < 18:
            return "base_core"
        return "med_lab"

    if npc_id == "chubby":
        if 18 <= h < 20:
            return "mine_surface"
        if h >= 20 or h < 6:
            exposed = _done(sess, "02-04") or _plot(sess, "tracked_chubby")
            if not exposed:
                return "underground_lab"
            return _stable_pick(_hash_seed("chubby_n", h), ("source_mine", "listen_station"))
        return _stable_pick(_hash_seed("chubby_d", h), ("source_mine", "base_core"))

    if npc_id == "jin":
        try:
            act = str(sess.current_node().act or "")
        except Exception:
            act = ""
        cave_unlocked = _coastal_cave_unlocked(sess)
        if act in ("prologue", "act1"):
            return "base_core"
        if act == "act2":
            go_cave = cave_unlocked and h % 3 == 0
            return "coastal_cave" if go_cave else "base_core"
        if act in ("act3", "finale"):
            grove_ok = _done(sess, "01-06")
            roll = _hash_seed("jin_late", h) % 5
            if roll == 1:
                return "coastal_cave"
            if grove_ok and roll >= 3:
                return "purify_grove"
            return "base_core"
        return "base_core"

    if npc_id == "echo_7":
        return "echo_spectral"

    if npc_id == "klein":
        return "sunk_lab"

    if npc_id == "elizabeth":
        return "comm_array"

    return "base_core"


def _coastal_cave_unlocked(sess: object) -> bool:
    from .explorer_access import zone_is_unlocked

    return zone_is_unlocked(sess, "coastal_cave")  # type: ignore[arg-type]


def npc_roaming_row(sess: object, npc_id: str) -> dict[str, str]:
    slug = npc_roaming_slug(sess, npc_id)
    return {
        "slug": slug,
        "location_zh": LOC_LABEL_ZH.get(slug, slug),
    }
