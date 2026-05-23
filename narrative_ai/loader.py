from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def load_world() -> dict[str, Any]:
    p = _data_dir() / "world.json"
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def load_player_variables() -> dict[str, Any]:
    p = _data_dir() / "player_variables.json"
    with p.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_npcs() -> dict[str, Any]:
    p = _data_dir() / "npcs.json"
    with p.open(encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)
    return raw


def get_npc(npc_id: str) -> dict[str, Any]:
    npcs = load_npcs()
    if npc_id not in npcs:
        raise KeyError(f"Unknown npc_id={npc_id!r}; known={sorted(npcs)}")
    return npcs[npc_id]
