from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class InteractionTurn:
    """One stored exchange line (summaries work best for prompting)."""

    role: Literal["player", "npc", "system"]
    summary: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmotionalState:
    """Numeric knobs that drive prose style thresholds (design doc §通用规则)."""

    trust: float = 50.0
    affinity: float = 50.0
    fear: float = 20.0
    secret_pull: float = 0.0  # inclination to reveal / break cover


def trust_band(trust: float) -> Literal["high", "mid", "low"]:
    if trust > 70:
        return "high"
    if trust >= 30:
        return "mid"
    return "low"


def trust_instructions(trust: float) -> str:
    band = trust_band(trust)
    if band == "high":
        return "信任偏高：用词可更亲切，可稍作解释或昵称试探，但不要OOC。"
    if band == "mid":
        return "信任中等：保持角色一贯风格，信息量中等。"
    return "信任偏低：回避、简短、少说内幕；可对玩家保持警惕。"


@dataclass
class SimulationSnapshot:
    """Optional lightweight state from the management layer."""

    resources: dict[str, int] = field(default_factory=dict)
    last_decision_tag: str | None = None
    last_decision_label_zh: str | None = None
    shoreline_intrusion_percent: float | None = None
    # SYNC / HUMAN / COUNCIL / … 见 data/player_variables.json 与 player_variables_endings_matrix.md
    hidden_vars: dict[str, float | int | str] = field(default_factory=dict)


@dataclass
class NpcMemoryStore:
    """
    Per-NPC session/world state for prompt injection.
    Long-term lines usually come from canon + designer edits; short-term is runtime.
    """

    npc_id: str
    long_term_notes: list[str] = field(default_factory=list)
    short_term: deque[InteractionTurn] = field(default_factory=lambda: deque(maxlen=5))
    emotional: EmotionalState = field(default_factory=EmotionalState)
    social_rumors: list[str] = field(default_factory=list)
    plot_flags: set[str] = field(default_factory=set)
    conspiracy_tier_unlocked: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def record_turn(self, turn: InteractionTurn) -> None:
        self.short_term.append(turn)

    def short_term_lines(self) -> list[str]:
        return [f"[{t.role}] {t.summary}" for t in self.short_term]
