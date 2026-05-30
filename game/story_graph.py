"""从 data/story_nodes.json 加载关键节点骨架（与对话节点表对齐）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ChoiceSpec:
    id: str
    label_zh: str
    next: str | None
    hidden_deltas: dict[str, float] = field(default_factory=dict)
    resource_deltas: dict[str, int] = field(default_factory=dict)
    npc_trust: dict[str, float] = field(default_factory=dict)
    flags_add: list[str] = field(default_factory=list)


@dataclass
class NodeSpec:
    id: str
    title_zh: str
    act: str
    chapter: int
    kind: str
    npc_focus: list[str]
    must_deliver_zh: list[str]
    next: str | None
    choices: list[ChoiceSpec] | None
    on_enter_hidden: dict[str, float]
    on_enter_plot: dict[str, int]
    requires_flags_any: list[str] | None
    skip_to: str | None
    player_objectives_zh: list[str] | None = None
    memory_flash_lines_zh: list[str] | None = None
    # 多轮固定选项对话（代替自由文本输入）；每轮含 NPC 台词与玩家选项
    pre_dialogue: list[dict[str, object]] | None = None
    # 静默运营 automation：在进入该节点并完成 on_enter_* 后对剧情相位赋值（对齐 docs/sim_*）。
    sandbox_enter_after_beat: bool = False
    sandbox_enter_min_world_days: int | None = None


def _parse_choice(raw: dict[str, Any]) -> ChoiceSpec:
    return ChoiceSpec(
        id=str(raw["id"]),
        label_zh=str(raw["label_zh"]),
        next=raw.get("next") if raw.get("next") is not None else None,
        hidden_deltas={k: float(v) for k, v in (raw.get("hidden_deltas") or {}).items()},
        resource_deltas={k: int(v) for k, v in (raw.get("resource_deltas") or {}).items()},
        npc_trust={k: float(v) for k, v in (raw.get("npc_trust") or {}).items()},
        flags_add=list(raw.get("flags_add") or []),
    )


def _parse_node(nid: str, raw: dict[str, Any]) -> NodeSpec:
    ch_raw = raw.get("choices")
    choices = [_parse_choice(c) for c in ch_raw] if ch_raw else None
    rf = raw.get("requires_flags_any")
    return NodeSpec(
        id=nid,
        title_zh=str(raw["title_zh"]),
        act=str(raw["act"]),
        chapter=int(raw["chapter"]),
        kind=str(raw["kind"]),
        npc_focus=list(raw.get("npc_focus") or []),
        must_deliver_zh=list(raw.get("must_deliver_zh") or []),
        next=raw.get("next") if raw.get("next") is not None else None,
        choices=choices,
        on_enter_hidden={k: float(v) for k, v in (raw.get("on_enter_hidden") or {}).items()},
        on_enter_plot={k: int(v) for k, v in (raw.get("on_enter_plot") or {}).items()},
        requires_flags_any=list(rf) if rf else None,
        skip_to=raw.get("skip_to"),
        player_objectives_zh=list(raw["player_objectives_zh"])
        if raw.get("player_objectives_zh")
        else None,
        memory_flash_lines_zh=list(raw["memory_flash_lines_zh"])
        if raw.get("memory_flash_lines_zh")
        else None,
        pre_dialogue=list(raw["pre_dialogue"]) if raw.get("pre_dialogue") else None,
        sandbox_enter_after_beat=bool(raw.get("sandbox_enter_after_beat", False)),
        sandbox_enter_min_world_days=(
            None
            if raw.get("sandbox_enter_min_world_days") is None
            else int(raw["sandbox_enter_min_world_days"])  # type: ignore[arg-type]
        ),
    )


def load_story_graph(path: Path | None = None) -> dict[str, NodeSpec]:
    base = path or Path(__file__).resolve().parent / "data" / "story_nodes.json"
    data = json.loads(base.read_text(encoding="utf-8"))
    nodes_raw: dict[str, Any] = data["nodes"]
    return {nid: _parse_node(nid, raw) for nid, raw in nodes_raw.items()}
