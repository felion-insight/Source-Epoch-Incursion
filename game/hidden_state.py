"""与 docs/player_variables_endings_matrix.md 对齐的隐藏变量与布尔剧情标记。"""

from __future__ import annotations

from dataclasses import dataclass, field


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


@dataclass
class PlayerHiddenVars:
    """核心隐藏变量（数值类 0–100；RESET 为整数次）。"""

    SYNC: float = 15.0
    HUMAN: float = 55.0
    COUNCIL: float = 50.0
    PURIFY: float = 20.0
    ECHO: float = 15.0
    INCURSION: float = 25.0
    RESET: int = 0
    INSIGHT: float = 10.0

    karen_defected: bool = False
    chubby_quest_complete: bool = False

    def apply_delta(self, key: str, delta: float | int) -> None:
        if key in {"SYNC", "HUMAN", "COUNCIL", "PURIFY", "ECHO", "INCURSION", "INSIGHT"}:
            cur = float(getattr(self, key))
            setattr(self, key, _clamp(cur + float(delta), 0.0, 100.0))
        elif key == "RESET":
            self.RESET = max(0, self.RESET + int(delta))

    def as_snapshot_dict(self) -> dict[str, float | int | bool]:
        return {
            "SYNC": self.SYNC,
            "HUMAN": self.HUMAN,
            "COUNCIL": self.COUNCIL,
            "PURIFY": self.PURIFY,
            "ECHO": self.ECHO,
            "INCURSION": self.INCURSION,
            "RESET": self.RESET,
            "INSIGHT": self.INSIGHT,
            "karen_defected": self.karen_defected,
            "chubby_quest_complete": self.chubby_quest_complete,
        }


@dataclass
class BaseResources:
    """docs/management_sim_design.md：四类核心资源（整数化便于 UI）。"""

    energy: int = 80
    food: int = 70
    medical: int = 40
    intel: int = 10

    def apply(self, **deltas: int) -> None:
        for k, v in deltas.items():
            cur = int(getattr(self, k))
            setattr(self, k, max(0, cur + int(v)))

    def as_dict(self) -> dict[str, int]:
        return {"energy": self.energy, "food": self.food, "medical": self.medical, "intel": self.intel}


@dataclass
class PlotFlags:
    """非数值剧情门闩（可选节点、设施分支等）。"""

    flags: set[str] = field(default_factory=set)

    def enable(self, name: str) -> None:
        self.flags.add(name)

    def has(self, name: str) -> bool:
        return name in self.flags

    def discard(self, name: str) -> None:
        self.flags.discard(name)
