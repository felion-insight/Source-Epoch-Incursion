"""结局条件与 docs/player_variables_endings_matrix.md §三 对齐的判定。"""

from __future__ import annotations

from dataclasses import dataclass

from .hidden_state import PlayerHiddenVars


@dataclass(frozen=True)
class EndingSpec:
    id: str
    title_zh: str
    hidden: bool = False


ENDING_CATALOG: tuple[EndingSpec, ...] = (
    EndingSpec("E1", "遗忘之约"),
    EndingSpec("E2", "新伊甸"),
    EndingSpec("E3", "神性监狱"),
    EndingSpec("E4", "统一寂静"),
    EndingSpec("E5", "循环继续"),
    EndingSpec("E6", "净空"),
    EndingSpec("E7", "先驱之路"),
    EndingSpec("E8", "真正的救赎", hidden=True),
)


def available_endings(v: PlayerHiddenVars) -> list[EndingSpec]:
    """矩阵「必要条件 / 排除条件」筛出 FIN-02 可选结局。"""
    out: list[EndingSpec] = []

    if (v.INCURSION > 60 or v.HUMAN < 30) and v.INSIGHT <= 50:
        out.append(ENDING_CATALOG[0])

    faction_max = max(v.COUNCIL, v.PURIFY, v.ECHO)
    if v.SYNC > 60 and v.HUMAN > 50 and faction_max <= 70:
        out.append(ENDING_CATALOG[1])

    if v.SYNC > 80 and v.COUNCIL > 60 and v.HUMAN <= 60:
        out.append(ENDING_CATALOG[2])

    if v.ECHO > 70 and v.HUMAN < 40 and v.PURIFY <= 30:
        out.append(ENDING_CATALOG[3])

    if v.COUNCIL > 70 and v.RESET <= 1:
        out.append(ENDING_CATALOG[4])

    if v.PURIFY > 60 and v.INCURSION > 50 and v.SYNC <= 40:
        out.append(ENDING_CATALOG[5])

    if v.SYNC > 90 and v.INSIGHT > 80:
        out.append(ENDING_CATALOG[6])

    if (
        v.INSIGHT > 80
        and v.HUMAN > 70
        and v.SYNC > 60
        and v.COUNCIL < 30
        and v.PURIFY < 30
        and v.ECHO < 30
    ):
        out.append(ENDING_CATALOG[7])

    seen: set[str] = set()
    uniq: list[EndingSpec] = []
    for e in out:
        if e.id not in seen:
            seen.add(e.id)
            uniq.append(e)
    return uniq
