"""源纪元 · 岸线侵入 — 游戏逻辑层（剧情状态、地图、HTTP API；与 docs/、narrative_ai/、web/ 对齐）。"""

from .bridge import (
    apply_management_decision,
    build_simulation_snapshot,
    default_source_agent,
    npc_agent_for,
    persist_source_exchange,
    record_player_line,
    source_session_from,
)
from .endings import ENDING_CATALOG, available_endings
from .facility_tech_tree import build_tech_tree_payload, get_tech_tree
from .hidden_state import BaseResources, PlayerHiddenVars, PlotFlags
from .management_turn import apply_management_tag
from .narrative_map import (
    FACILITY_MANAGEMENT_TAGS,
    facility_relevant_to_node,
    npc_is_current_focus,
    upgrade_choice_for_facility,
)
from .resource_activities import (
    build_activity_catalog_payload,
    get_activity,
    get_activities_for_region,
)
from .dispatch_system import (
    DISPATCH_NPC_INFO,
    build_dispatch_status_payload,
    build_facility_status_payload,
    simulate_dispatch_auto_decision,
)
from .session import GameSession
from .story_graph import load_story_graph
from .web_api import run_server

__all__ = [
    "GameSession",
    "PlayerHiddenVars",
    "BaseResources",
    "PlotFlags",
    "load_story_graph",
    "available_endings",
    "ENDING_CATALOG",
    "build_simulation_snapshot",
    "apply_management_decision",
    "apply_management_tag",
    "npc_agent_for",
    "record_player_line",
    "source_session_from",
    "persist_source_exchange",
    "default_source_agent",
    "run_server",
    "FACILITY_MANAGEMENT_TAGS",
    "facility_relevant_to_node",
    "npc_is_current_focus",
    "upgrade_choice_for_facility",
    # 模拟经营新系统
    "build_tech_tree_payload",
    "get_tech_tree",
    "build_activity_catalog_payload",
    "get_activity",
    "get_activities_for_region",
    "DISPATCH_NPC_INFO",
    "build_dispatch_status_payload",
    "build_facility_status_payload",
    "simulate_dispatch_auto_decision",
]
