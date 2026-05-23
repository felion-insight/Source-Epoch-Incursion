"""AI-assisted narrative / per-NPC agents for 源纪元 · 岸线侵入."""

from narrative_ai.config import Settings
from narrative_ai.generator import NarrativeGenerator
from narrative_ai.loader import get_npc, load_npcs, load_player_variables, load_world
from narrative_ai.management import DECISION_REGISTRY, ManagementReactionSpec, resolve_decision
from narrative_ai.memory import EmotionalState, InteractionTurn, NpcMemoryStore, SimulationSnapshot
from narrative_ai.npc_agent import NpcAgent
from narrative_ai.source_agent import SourceAgent, SourceSession
from narrative_ai.validators import mentions_recent_memory_heuristic

__all__ = [
    "Settings",
    "NarrativeGenerator",
    "load_world",
    "load_npcs",
    "load_player_variables",
    "get_npc",
    "NpcMemoryStore",
    "InteractionTurn",
    "EmotionalState",
    "SimulationSnapshot",
    "NpcAgent",
    "SourceAgent",
    "SourceSession",
    "DECISION_REGISTRY",
    "ManagementReactionSpec",
    "resolve_decision",
    "mentions_recent_memory_heuristic",
]
