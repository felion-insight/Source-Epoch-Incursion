"""基地核心自动化设施 — 生产子场景（10×10 网格、设备产线、NPC 岗位、剧情任务）。

入口：通过大地图基地核心设施交互进入。
"""

from __future__ import annotations

import copy
import random
import time
from typing import Any

from .sim_sandbox import append_bulletin_zh

POI_ID = "west_shaft"
POI_WORLD_X = 2460
POI_WORLD_Y = 3220
COMMAND_POI_ID = "underground_workshop_command"
COMMAND_POI_X = 2810
COMMAND_POI_Y = 2130

WORKSHOP_MAP_POIS: tuple[dict[str, Any], ...] = (
    {
        "id": POI_ID,
        "name_zh": "基地核心入口",
        "world_x": POI_WORLD_X,
        "world_y": POI_WORLD_Y,
        "blurb_zh": "西脉死路尽头",
    },
    {
        "id": COMMAND_POI_ID,
        "name_zh": "基地核心入口",
        "world_x": COMMAND_POI_X,
        "world_y": COMMAND_POI_Y,
        "blurb_zh": "基地核心",
    },
)

GRID_SIZE = 10
BASE_STORAGE_CAP = 72
BUILD_SITE_COST = {"energy": 30, "parts": 15}
# 首次进入工坊时，若基地资源不足则补至该下限（需覆盖：改造 15 零件 + 首台打印机 20 零件 + 余量）
WORKSHOP_ENTRY_FLOOR: dict[str, int] = {"energy": 100, "parts": 55}
# 改造完成后免费放置的起步设备（采矿→冶炼链，玩家只需再建打印机）
STARTER_DEVICE_LAYOUT: tuple[tuple[str, int, int], ...] = (
    ("miner", 1, 1),
    ("smelter", 3, 1),
    ("storage", 8, 1),
)
MAX_TICK_S = 120.0
DAILY_PASS_S = 360.0
DELEGATION_EFFICIENCY = 0.7
# 每个 NPC 最多同时管理的设备数
MAX_NPC_ASSIGNMENTS = 2
# 全局产线加速（周期缩短 ≈ 产出加快；1.35 → 约快 35%）
PRODUCTION_SPEED_MULT = 1.35
NPC_FATIGUE_THRESHOLD_MIN = 240.0
NPC_FATIGUE_PENALTY_PER_HOUR = 0.05
NPC_FATIGUE_TRUST_DRAIN = 1.0
GAME_MINUTES_PER_REAL_SECOND = 3.0
ABANDON_DEFICIT_DAYS = 3
REHAB_COST = {"energy": 50, "parts": 30}

DEFAULT_STOP_CAPS: dict[str, int] = {
    "parts": 50,
    "medical_pack": 24,
    "alloy": 40,
    "ore": 30,
    "components": 25,
}

RES_ZH: dict[str, str] = {
    "ore": "矿石",
    "alloy": "合金",
    "components": "电子元件",
    "source_crystal": "源能结晶",
    "source_ore": "源矿",
    "parts": "零件",
    "medical_pack": "医疗包",
}

BASE_RES_ZH: dict[str, str] = {
    "energy": "能源",
    "parts": "零件",
    "food": "食物",
    "medical": "医疗",
    "intel": "情报",
}


def _build_cost_zh(build: dict[str, Any]) -> str:
    order = ("energy", "parts", "food", "medical", "intel")
    parts: list[str] = []
    seen: set[str] = set()
    for k in order:
        v = int((build or {}).get(k, 0) or 0)
        if v > 0:
            parts.append(f"{BASE_RES_ZH.get(k, k)}×{v}")
            seen.add(k)
    for k, raw in (build or {}).items():
        if k in seen:
            continue
        v = int(raw or 0)
        if v > 0:
            parts.append(f"{BASE_RES_ZH.get(k, RES_ZH.get(k, k))}×{v}")
    return " · ".join(parts) if parts else "—"

WORKSHOP_ZONES: tuple[dict[str, Any], ...] = (
    {"id": "raw", "label_zh": "原料区", "x0": 0, "y0": 0, "x1": 4, "y1": 3},
    {"id": "production", "label_zh": "生产区", "x0": 2, "y0": 2, "x1": 8, "y1": 7},
    {"id": "storage", "label_zh": "仓储区", "x0": 7, "y0": 0, "x1": 10, "y1": 10},
    {"id": "power", "label_zh": "能源区", "x0": 0, "y0": 7, "x1": 4, "y1": 10},
)

DELEGATION_BUILD_ZONES: dict[str, tuple[int, int, int, int]] = {
    "miner": (0, 0, 4, 3),
    "smelter": (0, 0, 5, 4),
    "assembler": (2, 2, 8, 7),
    "refiner": (2, 4, 7, 8),
    "printer": (3, 2, 8, 6),
    "power_plant": (0, 7, 4, 10),
    "power_core": (0, 7, 4, 10),
    "storage": (7, 0, 10, 10),
}

DELEGATION_DEVICE_CHAIN: dict[str, tuple[str, ...]] = {
    "parts": ("miner", "smelter", "printer", "storage"),
    "medical_pack": ("miner", "smelter", "assembler", "printer", "storage"),
    "alloy": ("miner", "smelter", "storage"),
    "components": ("miner", "smelter", "assembler", "storage"),
    "source_crystal": ("refiner", "storage"),
    "ore": ("miner", "storage"),
}

TRADE_OFFERS: tuple[dict[str, Any], ...] = (
    {
        "id": "ore_for_energy",
        "label_zh": "10 矿石 → 15 能源",
        "give": {"ore": 10},
        "receive": {"energy": 15},
    },
    {
        "id": "alloy_for_energy",
        "label_zh": "3 合金 → 14 能源",
        "give": {"alloy": 3},
        "receive": {"energy": 14},
    },
    {
        "id": "components_for_intel",
        "label_zh": "2 电子元件 → 6 情报",
        "give": {"components": 2},
        "receive": {"intel": 6},
    },
    {
        "id": "source_crystal_for_parts",
        "label_zh": "1 源能结晶 → 12 零件",
        "give": {"source_crystal": 1},
        "receive": {"parts": 12},
    },
)

INDUSTRIAL_KEYS = ("ore", "alloy", "components", "source_crystal", "parts", "medical_pack")

DEVICE_CATALOG: dict[str, dict[str, Any]] = {
    "miner": {
        "label_zh": "采矿机",
        "w": 1,
        "h": 1,
        "build": {"energy": 10, "parts": 5},
        "cycle_s": 22.0,
        "energy_per_cycle": 0,
        "inputs": {},
        "outputs": {"ore": 1},
        "upgrade": {"cycle_s": 17.0, "cost": {"energy": 16, "parts": 8}},
    },
    "smelter": {
        "label_zh": "冶炼厂",
        "w": 2,
        "h": 1,
        "build": {"energy": 20, "parts": 8},
        "cycle_s": 26.0,
        "energy_per_cycle": 3,
        "inputs": {"ore": 1},
        "outputs": {"alloy": 1},
        "upgrade": {"cycle_s": 21.0, "energy_per_cycle": 2, "cost": {"energy": 26, "parts": 12}},
    },
    "storage": {
        "label_zh": "仓储柜",
        "w": 1,
        "h": 1,
        "build": {"energy": 4, "parts": 4},
        "storage_bonus": 24,
        "upgrade": {"storage_bonus": 48, "cost": {"energy": 12, "parts": 6}},
    },
    "power_plant": {
        "label_zh": "发电站",
        "w": 2,
        "h": 1,
        "build": {"energy": 20, "parts": 10},
        "cycle_s": 32.0,
        "energy_per_cycle": 0,
        "inputs": {"ore": 1},
        "outputs": {"base_energy": 15},
        "upgrade": {"cycle_s": 26.0, "outputs": {"base_energy": 20}, "cost": {"energy": 28, "parts": 14}},
    },
    "printer": {
        "label_zh": "3D 打印机",
        "w": 2,
        "h": 2,
        "build": {"energy": 30, "parts": 15},
        "cycle_s": 30.0,
        "energy_per_cycle": 4,
        "inputs": {"alloy": 1},
        "outputs": {"parts": 1},
        "alt_recipe": {
            "inputs": {"components": 1},
            "outputs": {"medical_pack": 3},
            "energy_per_cycle": 7,
        },
        "upgrade": {"cycle_mult": 0.82, "cost": {"energy": 40, "parts": 20}},
    },
    "assembler": {
        "label_zh": "组装厂",
        "w": 2,
        "h": 2,
        "build": {"energy": 36, "parts": 16},
        "cycle_s": 44.0,
        "energy_per_cycle": 5,
        "inputs": {"alloy": 1},
        "outputs": {"components": 1},
        "upgrade": {"cycle_s": 35.0, "energy_per_cycle": 4, "cost": {"energy": 40, "parts": 18}},
    },
    "refiner": {
        "label_zh": "源能精炼器",
        "w": 2,
        "h": 2,
        "build": {"energy": 50, "parts": 24},
        "cycle_s": 66.0,
        "energy_per_cycle": 12,
        "inputs": {"source_ore": 1},
        "outputs": {"source_crystal": 1},
        "accident_rate": 0.06,
        "upgrade": {"accident_rate": 0.03, "outputs": {"source_crystal": 1}, "cycle_s": 52.0, "cost": {"energy": 58, "parts": 28}},
    },
    "power_core": {
        "label_zh": "能源核心",
        "w": 3,
        "h": 3,
        "build": {"energy": 75, "parts": 38},
        "cycle_s": 96.0,
        "energy_per_cycle": 0,
        "inputs": {"source_crystal": 1},
        "outputs": {"base_energy": 130},
        "upgrade": {"outputs": {"base_energy": 165}, "cycle_s": 78.0, "cost": {"energy": 90, "parts": 45}},
    },
}

NPC_PROFILES: dict[str, dict[str, Any]] = {
    "chubby": {
        "label_zh": "小胖",
        "good": frozenset({"miner", "smelter", "assembler", "printer"}),
        "output_mult": 1.4,
        "accident_delta": 0.0,
        "bad_accident_delta": 0.15,
        "bad_devices": frozenset({"refiner"}),
        "bad_output_mult": 1.0,
        "event_rate": 0.05,
        "event_zh": "小胖在采矿机旁发现一块异常矿石，值得日后调查。",
    },
    "dr_lin": {
        "label_zh": "林博士",
        "good": frozenset({"refiner", "printer"}),
        "output_mult": 1.3,
        "accident_delta": -0.20,
        "bad_devices": frozenset({"miner"}),
        "bad_output_mult": 0.8,
        "event_rate": 0.10,
        "event_zh": "林博士在精炼器旁遭遇小事故，需要医疗关注。",
    },
    "karen": {
        "label_zh": "卡伦",
        "good": frozenset({"power_core", "power_plant", "storage"}),
        "output_mult": 1.2,
        "storage_bonus_mult": 1.15,
        "bad_devices": frozenset({"printer"}),
        "bad_output_mult": 0.8,
        "event_rate": 0.08,
        "event_zh": "卡伦报告能源消耗异常，疑似有外部渗透迹象。",
    },
    "jin": {
        "label_zh": "堇",
        "good": frozenset({"refiner"}),
        "output_mult": 1.15,
        "accident_delta": -0.05,
        "bad_devices": frozenset({"assembler"}),
        "bad_output_mult": 0.8,
        "event_rate": 0.06,
        "event_zh": "堇提醒过度开采可能激怒当地生态，建议节制。",
    },
    "temp_worker": {
        "label_zh": "临时帮工",
        "good": frozenset({"miner", "smelter", "assembler", "printer", "storage", "power_plant"}),
        "output_mult": 0.55,
        "accident_delta": 0.05,
        "bad_devices": frozenset({"refiner", "power_core"}),
        "bad_output_mult": 0.45,
        "event_rate": 0.0,
        "event_zh": "",
    },
}

MAX_ACTIVE_CONTRACTS = 3
MIN_ACTIVE_CONTRACTS = 2
CONTRACT_REFRESH_INTERVAL_S = 240.0
MAX_COMPLETED_CONTRACT_HISTORY = 24
HIDDEN_BRANCH_ROLL_CHANCE = 0.18

BASE_RES_ZH: dict[str, str] = {
    "energy": "能源",
    "food": "补给",
    "medical": "医疗",
    "intel": "情报",
    "parts": "零件",
}

RESOURCE_VALUE: dict[str, float] = {
    "ore": 1.0,
    "alloy": 2.0,
    "components": 4.0,
    "parts": 3.0,
    "medical_pack": 4.0,
    "source_crystal": 10.0,
}

CONTRACT_ISSUERS: tuple[str, ...] = (
    "基地调度",
    "后勤组",
    "西脉工段",
    "临时委托",
    "通讯中继",
    "匿名订单",
)

METRIC_LABELS: dict[str, tuple[str, ...]] = {
    "ore": ("原矿配额", "矿石批次", "粗炼原料指标"),
    "alloy": ("合金熔铸指标", "结构材料配额", "装甲板批次"),
    "components": ("元件装配指标", "电路板批次", "电子组件配额"),
    "source_crystal": ("结晶纯化指标", "源能批次", "晶体交付配额"),
    "parts": ("零件批次", "组装件指标", "维护备件配额"),
    "medical_pack": ("医疗包批次", "应急医药指标", "战地补给配额"),
}

CONTRACT_NEED_SPECS: tuple[dict[str, Any], ...] = (
    {"keys": ("parts",), "amount_range": (6, 16), "weight": 12},
    {"keys": ("alloy",), "amount_range": (5, 14), "weight": 10},
    {"keys": ("components",), "amount_range": (3, 9), "weight": 8},
    {"keys": ("medical_pack",), "amount_range": (3, 8), "weight": 7},
    {"keys": ("ore",), "amount_range": (10, 24), "weight": 9},
    {"keys": ("source_crystal",), "amount_range": (1, 2), "weight": 4},
    {"keys": ("parts", "alloy"), "amount_range": (4, 10), "weight": 6},
    {"keys": ("alloy", "components"), "amount_range": (3, 8), "weight": 5},
    {"keys": ("parts", "medical_pack"), "amount_range": (3, 7), "weight": 5},
)

HIDDEN_BRANCH_DEFS: tuple[dict[str, Any], ...] = (
    {
        "id": "comm_module",
        "plot_flags": ("workshop_comm_trade_unlocked", "comm_repair_module"),
        "requires_absent": ("workshop_comm_trade_unlocked",),
        "reveal_zh": "验收单里夹着一份加密通讯模块——与回声-7 的接触窗口似乎打开了。",
        "thematic_keys": frozenset({"parts", "components"}),
        "weight": 2,
    },
    {
        "id": "lin_lab",
        "plot_flags": ("lab_priority",),
        "requires_absent": ("lab_priority",),
        "reveal_zh": "林博士注意到这批医疗物资，发来一份加密样本清单……",
        "thematic_keys": frozenset({"medical_pack"}),
        "weight": 2,
        "trust_npc": "dr_lin",
        "trust_delta": 10.0,
    },
    {
        "id": "chubby_lab",
        "plot_flags": ("workshop_chubby_crystal_done",),
        "requires_absent": ("workshop_chubby_crystal_done",),
        "reveal_zh": "结晶验收后，小胖悄悄塞来一张地下实验室的旧门禁卡复印件。",
        "thematic_keys": frozenset({"source_crystal"}),
        "weight": 2,
    },
    {
        "id": "karen_cipher",
        "plot_flags": ("karen_cipher_hint",),
        "requires_absent": ("karen_cipher_hint",),
        "reveal_zh": "订单尾款里混进一段议会密文片段——卡伦似乎一直在暗中观察。",
        "thematic_keys": frozenset({"components"}),
        "weight": 2,
    },
    {
        "id": "source_resonator",
        "plot_flags": ("source_resonator_ready",),
        "requires_absent": ("source_resonator_ready",),
        "reveal_zh": "指标归档时，源的共振频率在日志里留下了一行无法删除的低语坐标。",
        "thematic_keys": frozenset({"source_crystal", "components"}),
        "weight": 1,
    },
    {
        "id": "purify_trade",
        "plot_flags": ("purify_trade_ack",),
        "requires_absent": ("purify_trade_ack",),
        "reveal_zh": "合金交割单被净空会截获并回签——他们愿意谈谈「引爆方案」。",
        "thematic_keys": frozenset({"alloy"}),
        "weight": 2,
    },
)

def _default_state() -> dict[str, Any]:
    return {
        "blueprint_known": False,
        "built": False,
        "abandoned": False,
        "delegation_on": False,
        "last_tick_ts": 0.0,
        "warehouse": {k: 0 for k in INDUSTRIAL_KEYS},
        "source_ore_buffer": 0,
        "cells": {},
        "task_delivered": {},
        "active_contracts": [],
        "completed_contracts": [],
        "contract_counter": 0,
        "contracts_seed": 0,
        "contracts_last_refresh_ts": 0.0,
        "events_log": [],
        "total_cycles": 0,
        "energy_deficit_days": 0,
        "npc_fatigue_minutes": {},
        "last_day_cycles": 0,
        "stop_caps": dict(DEFAULT_STOP_CAPS),
        "stop_caps_enabled": False,
        "delegation_action_zh": "",
        "starter_devices_placed": False,
        "npc_resting_ids": [],
    }


def _new_device_instance(device_type: str) -> dict[str, Any]:
    return {
        "type": device_type,
        "level": 1,
        "enabled": True,
        "npc_id": "",
        "progress": 0.0,
        "recipe": "default",
        "recipe_manual": False,
    }


def _normalize_printer_recipe(raw: Any) -> str:
    key = str(raw or "").strip().lower()
    if key in ("medical", "medical_pack", "med"):
        return "medical"
    return "default"


def _printer_recipe_zh(recipe: str) -> str:
    return "医疗包" if _normalize_printer_recipe(recipe) == "medical" else "零件"


def ensure_workshop_entry_resources(sess: Any) -> bool:
    """首次进入工坊链路时，保证玩家至少能完成改造并放置首台设备。"""
    if sess.plot.has("workshop_starter_floor_applied"):
        return False
    raised: list[str] = []
    for k, floor in WORKSHOP_ENTRY_FLOOR.items():
        cur = int(getattr(sess.resources, k, 0) or 0)
        if cur < int(floor):
            setattr(sess.resources, k, int(floor))
            label = {"energy": "能源", "parts": "零件"}.get(k, k)
            raised.append(f"{label}→{floor}")
    if not raised:
        sess.plot.enable("workshop_starter_floor_applied")
        return False
    sess.plot.enable("workshop_starter_floor_applied")
    append_bulletin_zh(sess, f"基地核心启动物资已调拨：{' · '.join(raised)}（仅首次）。")
    return True


def ensure_workshop_production_bootstrap(sess: Any) -> None:
    """已改造工坊但资源/设备不足时的一次性补救（旧存档或资源已花光）。"""
    if sess.plot.has("workshop_production_bootstrap_v1"):
        return
    state = _state(sess)
    if not state.get("built"):
        return
    changed: list[str] = []
    if not _devices_of_type(state, "smelter"):
        spec = DEVICE_CATALOG.get("smelter")
        if spec and _cells_free(state, 3, 1, int(spec["w"]), int(spec["h"])):
            state["cells"][_cell_key(3, 1)] = _new_device_instance("smelter")
            changed.append("补装冶炼厂")
    min_parts = 20
    min_energy = 40
    if int(sess.resources.parts) < min_parts:
        sess.resources.parts = min_parts
        changed.append(f"零件→{min_parts}")
    if int(sess.resources.energy) < min_energy:
        sess.resources.energy = min_energy
        changed.append(f"能源→{min_energy}")
    if not changed:
        sess.plot.enable("workshop_production_bootstrap_v1")
        return
    sess.plot.enable("workshop_production_bootstrap_v1")
    _maybe_log_event(state, f"起步补救：{' · '.join(changed)}。")
    _save(sess, state)
    append_bulletin_zh(sess, f"基地核心起步补救：{' · '.join(changed)}（仅一次）。")


def _place_starter_devices(state: dict[str, Any]) -> list[str]:
    if state.get("starter_devices_placed"):
        return []
    placed: list[str] = []
    for dtype, x, y in STARTER_DEVICE_LAYOUT:
        spec = DEVICE_CATALOG.get(dtype)
        if not spec:
            continue
        w, h = int(spec["w"]), int(spec["h"])
        if not _cells_free(state, x, y, w, h):
            continue
        state["cells"][_cell_key(x, y)] = _new_device_instance(dtype)
        placed.append(spec["label_zh"])
    if placed:
        state["starter_devices_placed"] = True
    return placed


def workshop_entry_pass(sess: Any) -> None:
    """进入工坊场景时的引导/bootstrap（资源下限 + 已改造但空网格的起步设备）。"""
    ensure_workshop_entry_resources(sess)
    ensure_workshop_production_bootstrap(sess)
    state = _state(sess)
    if not state.get("built"):
        _save(sess, state)
        return
    placed = _place_starter_devices(state)
    if placed:
        _maybe_log_event(state, f"启动配装：已免费放置 {'、'.join(placed)}。")
        append_bulletin_zh(sess, f"基地核心启动配装：{'、'.join(placed)} 已就绪，可立即开始生产。")
    if _ensure_active_contracts(sess, state):
        _maybe_log_event(state, "调度台发布了首批生产指标。")
    _save(sess, state)


def _state(sess: Any) -> dict[str, Any]:
    raw = getattr(sess, "underground_workshop", None)
    if not isinstance(raw, dict):
        raw = {}
    out = _default_state()
    out.update(raw)
    wh = out.get("warehouse")
    if not isinstance(wh, dict):
        wh = {}
    out["warehouse"] = {k: max(0, int(wh.get(k, 0) or 0)) for k in INDUSTRIAL_KEYS}
    out["source_ore_buffer"] = max(0, int(out.get("source_ore_buffer", 0) or 0))
    cells = out.get("cells")
    out["cells"] = dict(cells) if isinstance(cells, dict) else {}
    td = out.get("task_delivered")
    out["task_delivered"] = dict(td) if isinstance(td, dict) else {}
    el = out.get("events_log")
    out["events_log"] = list(el)[-20:] if isinstance(el, list) else []
    out["blueprint_known"] = bool(out.get("blueprint_known", False))
    out["built"] = bool(out.get("built", False))
    out["delegation_on"] = bool(out.get("delegation_on", False))
    out["last_tick_ts"] = float(out.get("last_tick_ts") or 0.0)
    out["total_cycles"] = max(0, int(out.get("total_cycles", 0) or 0))
    out["abandoned"] = bool(out.get("abandoned", False))
    out["energy_deficit_days"] = max(0, int(out.get("energy_deficit_days", 0) or 0))
    out["last_day_cycles"] = max(0, int(out.get("last_day_cycles", 0) or 0))
    nf = out.get("npc_fatigue_minutes")
    out["npc_fatigue_minutes"] = dict(nf) if isinstance(nf, dict) else {}
    sc = out.get("stop_caps")
    caps = dict(DEFAULT_STOP_CAPS)
    if isinstance(sc, dict):
        for k, v in sc.items():
            if k in INDUSTRIAL_KEYS:
                caps[k] = max(0, int(v or 0))
    # 旧存档/误设 ore=1 会导致采矿机产出 1 个后永久停线
    if int(caps.get("ore", 0) or 0) == 1:
        caps["ore"] = int(DEFAULT_STOP_CAPS["ore"])
    out["stop_caps"] = caps
    out["stop_caps_enabled"] = bool(out.get("stop_caps_enabled", True))
    out["delegation_action_zh"] = str(out.get("delegation_action_zh") or "")
    out["starter_devices_placed"] = bool(out.get("starter_devices_placed", False))
    nri = out.get("npc_resting_ids")
    out["npc_resting_ids"] = [str(s) for s in nri if isinstance(s, str) and s.strip()] if isinstance(nri, list) else []
    ac = out.get("active_contracts")
    out["active_contracts"] = [dict(c) for c in ac if isinstance(c, dict)] if isinstance(ac, list) else []
    cc = out.get("completed_contracts")
    out["completed_contracts"] = [dict(c) for c in cc if isinstance(c, dict)][-MAX_COMPLETED_CONTRACT_HISTORY:] if isinstance(cc, list) else []
    out["contract_counter"] = max(0, int(out.get("contract_counter", 0) or 0))
    seed = int(out.get("contracts_seed", 0) or 0)
    if seed <= 0:
        seed = random.randint(1, 2_000_000_000)
    out["contracts_seed"] = seed
    out["contracts_last_refresh_ts"] = float(out.get("contracts_last_refresh_ts") or 0.0)
    for inst in out["cells"].values():
        if not isinstance(inst, dict):
            continue
        if str(inst.get("type") or "") == "printer":
            inst["recipe"] = _normalize_printer_recipe(inst.get("recipe"))
            inst.setdefault("recipe_manual", False)
    return out


def _persist_workshop_state(state: dict[str, Any]) -> dict[str, Any]:
    """深拷贝工坊持久化状态，避免浅拷贝导致仓库/设备进度在会话间丢失。"""
    wh = state.get("warehouse") if isinstance(state.get("warehouse"), dict) else {}
    cells = state.get("cells") if isinstance(state.get("cells"), dict) else {}
    active = state.get("active_contracts") if isinstance(state.get("active_contracts"), list) else []
    completed = state.get("completed_contracts") if isinstance(state.get("completed_contracts"), list) else []
    events = state.get("events_log") if isinstance(state.get("events_log"), list) else []
    fatigue = state.get("npc_fatigue_minutes") if isinstance(state.get("npc_fatigue_minutes"), dict) else {}
    stop_caps = state.get("stop_caps") if isinstance(state.get("stop_caps"), dict) else {}
    task_delivered = state.get("task_delivered") if isinstance(state.get("task_delivered"), dict) else {}
    return {
        "blueprint_known": bool(state.get("blueprint_known", False)),
        "built": bool(state.get("built", False)),
        "abandoned": bool(state.get("abandoned", False)),
        "delegation_on": bool(state.get("delegation_on", False)),
        "last_tick_ts": float(state.get("last_tick_ts") or 0.0),
        "warehouse": {k: max(0, int(wh.get(k, 0) or 0)) for k in INDUSTRIAL_KEYS},
        "source_ore_buffer": max(0, int(state.get("source_ore_buffer", 0) or 0)),
        "cells": {str(k): copy.deepcopy(v) for k, v in cells.items() if isinstance(v, dict)},
        "task_delivered": dict(task_delivered),
        "active_contracts": [copy.deepcopy(c) for c in active if isinstance(c, dict)],
        "completed_contracts": [copy.deepcopy(c) for c in completed if isinstance(c, dict)],
        "contract_counter": max(0, int(state.get("contract_counter", 0) or 0)),
        "contracts_seed": max(1, int(state.get("contracts_seed", 0) or 0)),
        "contracts_last_refresh_ts": float(state.get("contracts_last_refresh_ts") or 0.0),
        "events_log": list(events)[-20:],
        "total_cycles": max(0, int(state.get("total_cycles", 0) or 0)),
        "energy_deficit_days": max(0, int(state.get("energy_deficit_days", 0) or 0)),
        "npc_fatigue_minutes": dict(fatigue),
        "last_day_cycles": max(0, int(state.get("last_day_cycles", 0) or 0)),
        "stop_caps": dict(_normalize_stop_caps(stop_caps)),
        "stop_caps_enabled": bool(state.get("stop_caps_enabled", False)),
        "delegation_action_zh": str(state.get("delegation_action_zh") or ""),
        "starter_devices_placed": bool(state.get("starter_devices_placed", False)),
        "npc_resting_ids": list(state.get("npc_resting_ids") or []),
    }
    return out


def _save(sess: Any, state: dict[str, Any]) -> None:
    """持久化工坊状态到会话对象；存档由前端 localStorage 负责。"""
    setattr(sess, "underground_workshop", _persist_workshop_state(state))


def workshop_leave(sess: Any) -> None:
    """离开工坊界面前刷一次 tick 并落盘，避免资源只留在内存快照里。"""
    _auto_tick(sess)
    state = _state(sess)
    _save(sess, state)


def coerce_persisted_workshop(raw: Any) -> dict[str, Any]:
    """把会话存档/API 快照统一还原为可持久化的工坊 state。"""
    if not isinstance(raw, dict) or not raw:
        return {}
    if isinstance(raw.get("cells"), dict):
        return copy.deepcopy(raw)
    devices = raw.get("devices")
    if not isinstance(devices, list):
        return {}
    cells: dict[str, dict[str, Any]] = {}
    for dev in devices:
        if not isinstance(dev, dict):
            continue
        ax = dev.get("anchor_x")
        ay = dev.get("anchor_y")
        dtype = str(dev.get("type") or "").strip()
        if ax is None or ay is None or not dtype:
            continue
        cells[f"{int(ax)},{int(ay)}"] = {
            "type": dtype,
            "level": max(1, int(dev.get("level", 1) or 1)),
            "enabled": bool(dev.get("enabled", True)),
            "npc_id": str(dev.get("npc_id") or ""),
            "progress": float(dev.get("progress", 0.0) or 0.0),
            "recipe": _normalize_printer_recipe(dev.get("recipe")),
            "recipe_manual": bool(dev.get("recipe_manual", False)),
        }
    wh = raw.get("warehouse") if isinstance(raw.get("warehouse"), dict) else {}
    return {
        "blueprint_known": bool(raw.get("blueprint_known", False)),
        "built": bool(raw.get("built", False)),
        "abandoned": bool(raw.get("abandoned", False)),
        "delegation_on": bool(raw.get("delegation_on", False)),
        "last_tick_ts": float(raw.get("last_tick_ts") or 0.0),
        "warehouse": {k: max(0, int(wh.get(k, 0) or 0)) for k in INDUSTRIAL_KEYS},
        "source_ore_buffer": max(0, int(raw.get("source_ore_buffer", 0) or 0)),
        "cells": cells,
        "starter_devices_placed": bool(raw.get("starter_devices_placed", bool(cells))),
        "stop_caps": dict(raw.get("stop_caps") or DEFAULT_STOP_CAPS),
        "stop_caps_enabled": bool(raw.get("stop_caps_enabled", False)),
        "active_contracts": [copy.deepcopy(c) for c in (raw.get("active_contracts") or []) if isinstance(c, dict)],
        "completed_contracts": [copy.deepcopy(c) for c in (raw.get("completed_contracts") or []) if isinstance(c, dict)],
        "contract_counter": max(0, int(raw.get("contract_counter", 0) or 0)),
        "contracts_seed": max(0, int(raw.get("contracts_seed", 0) or 0)),
        "contracts_last_refresh_ts": float(raw.get("contracts_last_refresh_ts") or 0.0),
        "events_log": list(raw.get("events_log") or [])[-20:],
        "total_cycles": max(0, int(raw.get("total_cycles", 0) or 0)),
        "energy_deficit_days": max(0, int(raw.get("energy_deficit_days", 0) or 0)),
        "npc_fatigue_minutes": dict(raw.get("npc_fatigue_minutes") or {}),
        "last_day_cycles": max(0, int(raw.get("last_day_cycles", 0) or 0)),
        "delegation_action_zh": str(raw.get("delegation_action_zh") or ""),
        "task_delivered": dict(raw.get("task_delivered") or {}),
        "npc_resting_ids": list(raw.get("npc_resting_ids") or []),
    }


def _contract_rng(state: dict[str, Any]) -> random.Random:
    seed = int(state.get("contracts_seed", 1) or 1) ^ (int(state.get("contract_counter", 0) or 0) * 9973)
    return random.Random(seed & 0xFFFFFFFF)


def _resource_bundle_value(resources: dict[str, int]) -> float:
    return sum(float(RESOURCE_VALUE.get(k, 2.0)) * max(0, int(v)) for k, v in resources.items())


def _format_resources_zh(resources: dict[str, int]) -> str:
    parts: list[str] = []
    for k, v in resources.items():
        n = int(v or 0)
        if n <= 0:
            continue
        label = RES_ZH.get(k) or BASE_RES_ZH.get(k) or k
        parts.append(f"{label} ×{n}")
    return " · ".join(parts) if parts else "—"


def _generate_contract_rewards(need: dict[str, int], rng: random.Random) -> tuple[dict[str, int], dict[str, int]]:
    wh_reward: dict[str, int] = {}
    base_reward: dict[str, int] = {}
    total = _resource_bundle_value(need)
    payout = max(2.0, total * rng.uniform(0.45, 0.82))
    candidates = [k for k in INDUSTRIAL_KEYS if k not in need or rng.random() < 0.35]
    if not candidates:
        candidates = list(INDUSTRIAL_KEYS)
    rng.shuffle(candidates)
    remaining = payout
    num_types = rng.randint(1, min(2, len(candidates)))
    for idx, key in enumerate(candidates[:num_types]):
        if remaining <= 0:
            break
        if idx == num_types - 1:
            share = remaining
        else:
            share = rng.uniform(0.35, 0.7) * remaining
        unit = float(RESOURCE_VALUE.get(key, 2.0))
        amount = max(1, int(round(share / unit)))
        wh_reward[key] = wh_reward.get(key, 0) + amount
        remaining = max(0.0, remaining - share)
    if rng.random() < 0.28:
        base_reward["energy"] = rng.randint(4, 14)
    if rng.random() < 0.14:
        base_reward["intel"] = rng.randint(1, 5)
    if rng.random() < 0.1:
        base_reward["parts"] = rng.randint(2, 8)
    return wh_reward, base_reward


def _maybe_roll_hidden_branch(sess: Any, need: dict[str, int], rng: random.Random) -> dict[str, Any] | None:
    if rng.random() > HIDDEN_BRANCH_ROLL_CHANCE:
        return None
    keys = set(need.keys())
    eligible: list[dict[str, Any]] = []
    for hb in HIDDEN_BRANCH_DEFS:
        if any(sess.plot.has(str(flag)) for flag in hb.get("requires_absent", ())):
            continue
        thematic = hb.get("thematic_keys")
        if thematic and not (keys & set(thematic)):
            continue
        eligible.append(hb)
    if not eligible:
        return None
    pick = rng.choices(eligible, weights=[int(h.get("weight", 1) or 1) for h in eligible], k=1)[0]
    branch: dict[str, Any] = {
        "id": pick["id"],
        "plot_flags": list(pick.get("plot_flags") or ()),
        "reveal_zh": str(pick.get("reveal_zh") or ""),
    }
    if pick.get("trust_npc"):
        branch["trust_npc"] = pick["trust_npc"]
        branch["trust_delta"] = float(pick.get("trust_delta", 8.0) or 8.0)
    return branch


def _generate_contract(sess: Any, state: dict[str, Any]) -> dict[str, Any]:
    rng = _contract_rng(state)
    state["contract_counter"] = int(state.get("contract_counter", 0) or 0) + 1
    spec = rng.choices(
        list(CONTRACT_NEED_SPECS),
        weights=[int(s.get("weight", 1) or 1) for s in CONTRACT_NEED_SPECS],
        k=1,
    )[0]
    lo, hi = spec.get("amount_range") or (3, 8)
    need: dict[str, int] = {}
    for key in spec.get("keys") or ():
        need[str(key)] = rng.randint(int(lo), int(hi))
    primary = next(iter(need.keys()), "parts")
    labels = METRIC_LABELS.get(primary, ("生产指标",))
    label_zh = rng.choice(labels)
    issuer_zh = rng.choice(CONTRACT_ISSUERS)
    reward_wh, reward_base = _generate_contract_rewards(need, rng)
    hidden_branch = _maybe_roll_hidden_branch(sess, need, rng)
    return {
        "id": f"wc{int(state['contract_counter']):05d}",
        "label_zh": label_zh,
        "issuer_zh": issuer_zh,
        "need": need,
        "reward_wh": reward_wh,
        "reward_base": reward_base,
        "published_ts": time.time(),
        "hidden_branch": hidden_branch,
    }


def _ensure_active_contracts(sess: Any, state: dict[str, Any], *, force_one: bool = False) -> bool:
    if not state.get("built") or state.get("abandoned"):
        return False
    changed = False
    active = list(state.get("active_contracts") or [])
    now = time.time()
    last = float(state.get("contracts_last_refresh_ts") or 0.0)
    if last <= 0:
        state["contracts_last_refresh_ts"] = now
        last = now
    while len(active) < MIN_ACTIVE_CONTRACTS:
        active.append(_generate_contract(sess, state))
        changed = True
    if force_one:
        if len(active) < MAX_ACTIVE_CONTRACTS:
            active.append(_generate_contract(sess, state))
            state["contracts_last_refresh_ts"] = now
            changed = True
    elif (
        len(active) >= MIN_ACTIVE_CONTRACTS
        and len(active) < MAX_ACTIVE_CONTRACTS
        and now - last >= CONTRACT_REFRESH_INTERVAL_S
    ):
        active.append(_generate_contract(sess, state))
        state["contracts_last_refresh_ts"] = now
        changed = True
    while len(active) > MAX_ACTIVE_CONTRACTS:
        active.pop()
        changed = True
    state["active_contracts"] = active[:MAX_ACTIVE_CONTRACTS]
    return changed


def _grant_contract_rewards(sess: Any, state: dict[str, Any], contract: dict[str, Any]) -> dict[str, int]:
    granted: dict[str, int] = {}
    wh = state["warehouse"]
    for k, v in dict(contract.get("reward_wh") or {}).items():
        n = max(0, int(v or 0))
        if n <= 0:
            continue
        wh[k] = int(wh.get(k, 0)) + n
        granted[k] = granted.get(k, 0) + n
    # 统一使用 apply() 修改基地资源，保证数值在安全范围内
    base_deltas: dict[str, int] = {}
    for k, v in dict(contract.get("reward_base") or {}).items():
        n = max(0, int(v or 0))
        if n <= 0:
            continue
        base_deltas[k] = n
        granted[k] = granted.get(k, 0) + n
    if base_deltas:
        sess.resources.apply(**base_deltas)
    return granted


def _apply_hidden_branch(sess: Any, contract: dict[str, Any]) -> str:
    branch = contract.get("hidden_branch")
    if not isinstance(branch, dict):
        return ""
    reveal = str(branch.get("reveal_zh") or "").strip()
    for flag in branch.get("plot_flags") or ():
        fid = str(flag or "").strip()
        if fid:
            sess.plot.enable(fid)
    trust_npc = str(branch.get("trust_npc") or "").strip()
    if trust_npc:
        try:
            st = sess.get_memory_store(trust_npc)
            delta = float(branch.get("trust_delta", 8.0) or 8.0)
            st.emotional.trust = min(100.0, st.emotional.trust + delta)
            sess.save_memory_store(st)
        except Exception:
            pass
    return reveal


def _has_workshop_device(state: dict[str, Any], dtype: str) -> bool:
    target = str(dtype or "").strip()
    return any(str(v.get("type") or "") == target for v in (state.get("cells") or {}).values())


def _player_knows_resource(sess: Any, state: dict[str, Any], key: str) -> bool:
    """玩家是否已在剧情/经历中「认识」该资源（否则 UI 奖励显示为 ???）。"""
    k = str(key or "").strip()
    if not k or k == "_mystery":
        return False
    completed = frozenset(getattr(sess, "completed_nodes", []) or [])
    wh = state.get("warehouse") or {}
    if k in ("ore", "alloy", "parts", "energy", "food"):
        return True
    if k in ("medical", "medical_pack"):
        return (
            _has_workshop_device(state, "printer")
            or int(wh.get("medical_pack", 0) or 0) > 0
            or int(getattr(sess.resources, "medical", 0) or 0) > 0
            or bool(completed & {"01-04", "01-07", "02-01"})
        )
    if k == "components":
        return (
            _has_workshop_device(state, "assembler")
            or int(wh.get("components", 0) or 0) > 0
            or bool(completed & {"01-02", "01-04", "01-07"})
        )
    if k == "source_crystal":
        return (
            _has_workshop_device(state, "refiner")
            or int(wh.get("source_crystal", 0) or 0) > 0
            or sess.plot.has("workshop_chubby_crystal_done")
            or bool(completed & {"02-01", "02-02", "02-03"})
        )
    if k == "intel":
        return (
            int(getattr(sess.resources, "intel", 0) or 0) > 0
            or comm_trade_available(sess)
            or bool(completed & {"01-02", "01-04"})
        )
    return True


def _resource_label_zh(key: str) -> str:
    k = str(key or "").strip()
    return RES_ZH.get(k) or BASE_RES_ZH.get(k) or k


def _contract_reward_items_ui(
    sess: Any, state: dict[str, Any], contract: dict[str, Any], *, done: bool = False
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for bucket in (contract.get("reward_wh") or {}, contract.get("reward_base") or {}):
        for k, v in dict(bucket).items():
            n = int(v or 0)
            if n <= 0:
                continue
            known = done or _player_knows_resource(sess, state, str(k))
            label = _resource_label_zh(str(k)) if known else "???"
            items.append(
                {
                    "key": k,
                    "label_zh": label,
                    "amount": n if known else 0,
                    "display_zh": f"{label} ×{n}" if known else "???",
                    "hidden": not known,
                }
            )
    if not done and contract.get("hidden_branch"):
        items.append(
            {
                "key": "_mystery",
                "label_zh": "???",
                "amount": 0,
                "display_zh": "???",
                "hidden": True,
            }
        )
    return items


def _format_reward_display_zh(reward_items: list[dict[str, Any]]) -> str:
    parts = [str(item.get("display_zh") or item.get("label_zh") or "???") for item in reward_items if item]
    return " · ".join(parts) if parts else "—"


def _contract_to_ui(sess: Any, state: dict[str, Any], contract: dict[str, Any], *, done: bool = False) -> dict[str, Any]:
    wh = state["warehouse"]
    need = dict(contract.get("need") or {})
    need_items: list[dict[str, Any]] = []
    total_need = 0
    total_have = 0
    for k, v in need.items():
        need_i = max(0, int(v))
        have = max(0, int(wh.get(k, 0)))
        met = have >= need_i
        pct = min(100, int(have * 100 / need_i)) if need_i > 0 else 100
        label_zh = _resource_label_zh(str(k))
        need_items.append(
            {
                "key": k,
                "label_zh": label_zh,
                "have": have,
                "need": need_i,
                "met": met,
                "pct": pct,
            }
        )
        total_need += need_i
        total_have += min(have, need_i)
    progress_pct = min(100, int(total_have * 100 / total_need)) if total_need > 0 else (100 if done else 0)
    can_deliver = (not done) and all(item["met"] for item in need_items)
    if done:
        status = "done"
        status_zh = "已达成"
    elif can_deliver:
        status = "ready"
        status_zh = "可交付"
    elif progress_pct > 0:
        status = "progress"
        status_zh = "进行中"
    else:
        status = "pending"
        status_zh = "待生产"
    reward_items = _contract_reward_items_ui(sess, state, contract, done=done)
    reward_zh = _format_reward_display_zh(reward_items)
    published_ts = float(contract.get("published_ts") or 0.0)
    is_new = (not done) and published_ts > 0 and (time.time() - published_ts) < 90.0
    return {
        "id": contract.get("id"),
        "issuer_zh": contract.get("issuer_zh") or "委托",
        "done": done,
        "need_items": need_items,
        "progress_pct": progress_pct,
        "status": status,
        "status_zh": status_zh,
        "progress_zh": " · ".join(f"{item['label_zh']} {item['have']}/{item['need']}" for item in need_items),
        "need_display_zh": " · ".join(f"{item['label_zh']} {item['have']}/{item['need']}" for item in need_items),
        "can_deliver": can_deliver,
        "reward_zh": reward_zh,
        "reward_items": reward_items,
        "is_new": is_new,
    }


def _build_tasks_ui(sess: Any, state: dict[str, Any]) -> list[dict[str, Any]]:
    tasks_ui: list[dict[str, Any]] = []
    for contract in state.get("active_contracts") or []:
        if isinstance(contract, dict):
            tasks_ui.append(_contract_to_ui(sess, state, contract, done=False))
    for contract in reversed(state.get("completed_contracts") or []):
        if isinstance(contract, dict):
            tasks_ui.append(_contract_to_ui(sess, state, contract, done=True))
    return tasks_ui


def _cell_key(x: int, y: int) -> str:
    return f"{x},{y}"


def _parse_cell_key(key: str) -> tuple[int, int]:
    a, b = key.split(",", 1)
    return int(a), int(b)


def _device_at(state: dict[str, Any], x: int, y: int) -> tuple[str, dict[str, Any]] | None:
    for key, inst in state["cells"].items():
        ax, ay = _parse_cell_key(key)
        spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
        if not spec:
            continue
        w, h = int(spec["w"]), int(spec["h"])
        if ax <= x < ax + w and ay <= y < ay + h:
            return key, inst
    return None


def _storage_cap(state: dict[str, Any]) -> int:
    cap = BASE_STORAGE_CAP
    for key, inst in state["cells"].items():
        spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
        if spec and spec.get("storage_bonus"):
            lvl = max(1, int(inst.get("level", 1) or 1))
            bonus = int(spec["storage_bonus"])
            if lvl >= 2 and spec.get("upgrade", {}).get("storage_bonus"):
                bonus = int(spec["upgrade"]["storage_bonus"])
            cap += bonus
    return cap


def _warehouse_total(state: dict[str, Any]) -> int:
    return sum(int(state["warehouse"].get(k, 0) or 0) for k in INDUSTRIAL_KEYS)


def _can_store(state: dict[str, Any], outputs: dict[str, float]) -> bool:
    add = sum(max(0, int(round(v))) for v in outputs.values() if v > 0)
    if add <= 0:
        return True
    return _warehouse_total(state) + add <= _storage_cap(state)


def _normalize_stop_caps(raw: dict[str, Any] | None) -> dict[str, int]:
    caps = dict(DEFAULT_STOP_CAPS)
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in INDUSTRIAL_KEYS:
                caps[k] = max(0, int(v or 0))
    return caps


def _output_blocked_by_cap(state: dict[str, Any], outputs: dict[str, float]) -> bool:
    if not state.get("stop_caps_enabled", True):
        return False
    caps = _normalize_stop_caps(state.get("stop_caps"))
    wh = state["warehouse"]
    for k, v in outputs.items():
        if k == "base_energy" or float(v) <= 0:
            continue
        cap = caps.get(k)
        if cap is not None and int(cap) > 0 and int(wh.get(k, 0)) >= int(cap):
            return True
    return False


def _footprint_tiles(ax: int, ay: int, w: int, h: int) -> set[tuple[int, int]]:
    return {(ax + dx, ay + dy) for dy in range(h) for dx in range(w)}


def _border_neighbors(ax: int, ay: int, w: int, h: int) -> set[tuple[int, int]]:
    tiles = _footprint_tiles(ax, ay, w, h)
    out: set[tuple[int, int]] = set()
    for x, y in tiles:
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in tiles and 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                out.add((nx, ny))
    return out


def _has_adjacent_storage(state: dict[str, Any], ax: int, ay: int, w: int, h: int) -> bool:
    for nx, ny in _border_neighbors(ax, ay, w, h):
        hit = _device_at(state, nx, ny)
        if hit and str(hit[1].get("type") or "") == "storage":
            return True
    return False


def _adjacent_anchors(state: dict[str, Any], ax: int, ay: int, w: int, h: int) -> list[tuple[int, int, dict[str, Any], dict[str, Any]]]:
    seen: set[str] = set()
    found: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for nx, ny in _border_neighbors(ax, ay, w, h):
        hit = _device_at(state, nx, ny)
        if not hit:
            continue
        key, inst = hit
        if key in seen:
            continue
        seen.add(key)
        nax, nay = _parse_cell_key(key)
        spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
        if spec:
            found.append((nax, nay, inst, spec))
    return found


def _logistics_ok(
    state: dict[str, Any],
    ax: int,
    ay: int,
    w: int,
    h: int,
    recipe: dict[str, Any],
) -> tuple[bool, str | None]:
    inputs = dict(recipe.get("inputs") or {})
    if not inputs:
        return True, None
    has_storage = _has_adjacent_storage(state, ax, ay, w, h)
    need_pull: list[str] = []
    for res in inputs:
        if res == "source_ore":
            continue
        upstream = False
        for nax, nay, ninst, nspec in _adjacent_anchors(state, ax, ay, w, h):
            nrecipe = _resolved_recipe(nspec, ninst)
            if res in (nrecipe.get("outputs") or {}):
                upstream = True
                break
        if not has_storage and not upstream:
            need_pull.append(res)
    if need_pull:
        labels = "、".join(RES_ZH.get(r, r) for r in need_pull)
        return False, f"需邻接仓储或上游设备：缺 {labels}"
    return True, None


def _inputs_available(state: dict[str, Any], sess: Any, inputs: dict[str, float]) -> tuple[bool, list[str]]:
    wh = state["warehouse"]
    missing: list[str] = []
    for k, v in inputs.items():
        need = max(0, int(round(float(v))))
        if k == "source_ore":
            if int(state.get("source_ore_buffer", 0)) < need:
                missing.append(k)
        elif int(wh.get(k, 0)) < need:
            missing.append(k)
    if missing:
        return False, missing
    return True, []


def _device_rate_zh(spec: dict[str, Any], inst: dict[str, Any]) -> str:
    if spec.get("storage_bonus"):
        lvl = max(1, int(inst.get("level", 1) or 1))
        bonus = int(spec["storage_bonus"])
        if lvl >= 2 and spec.get("upgrade", {}).get("storage_bonus"):
            bonus = int(spec["upgrade"]["storage_bonus"])
        return f"仓储+{bonus}"
    recipe = _resolved_recipe(spec, inst)
    cycle_s = max(1, int(round(float(recipe["cycle_s"]))))
    outs = recipe.get("outputs") or {}
    if not outs:
        return ""
    parts = []
    for k, v in outs.items():
        if k == "base_energy":
            parts.append(f"能源+{int(v)}")
        else:
            parts.append(f"{RES_ZH.get(k, k)}+{int(round(float(v)))}")
    return f"{'/'.join(parts)}/{cycle_s}s"


def _evaluate_device_status(
    sess: Any,
    state: dict[str, Any],
    key: str,
    inst: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    if not inst.get("enabled", True):
        return {"code": "off", "label_zh": "已暂停", "missing": []}
    if spec.get("storage_bonus"):
        return {"code": "storage", "label_zh": "仓储扩展", "missing": []}
    npc_id = str(inst.get("npc_id") or "").strip()
    if not npc_id or npc_id == "temp_worker":
        return {"code": "idle", "label_zh": "待派遣人员", "missing": []}
    ax, ay = _parse_cell_key(key)
    w, h = int(spec["w"]), int(spec["h"])
    recipe = _resolved_recipe(spec, inst)
    outs = {k: float(v) for k, v in (recipe.get("outputs") or {}).items() if k != "base_energy"}
    if _output_blocked_by_cap(state, outs):
        hit = next((RES_ZH.get(k, k) for k in outs if int(state["warehouse"].get(k, 0)) >= int(_normalize_stop_caps(state.get("stop_caps")).get(k, 999999))), "")
        return {"code": "cap", "label_zh": f"已达库存上限（{hit}）", "missing": []}
    if outs and not _can_store(state, outs):
        return {"code": "full", "label_zh": "仓库已满", "missing": []}
    log_ok, log_msg = _logistics_ok(state, ax, ay, w, h, recipe)
    if not log_ok:
        return {"code": "logistics", "label_zh": log_msg or "物流未连通", "missing": []}
    energy_need = int(recipe.get("energy_per_cycle", 0))
    if energy_need > 0 and sess.resources.energy < energy_need:
        return {"code": "energy", "label_zh": "基地能源不足", "missing": []}
    _, missing = _inputs_available(state, sess, recipe.get("inputs") or {})
    if missing:
        labels = "、".join(RES_ZH.get(m, m) for m in missing)
        return {"code": "materials", "label_zh": f"缺原料：{labels}", "missing": missing}
    return {"code": "running", "label_zh": "运行中", "missing": []}


def _compute_logistics_links(state: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int, int, str]] = set()
    for key, inst in state["cells"].items():
        ax, ay = _parse_cell_key(key)
        spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
        if not spec or spec.get("storage_bonus"):
            continue
        w, h = int(spec["w"]), int(spec["h"])
        recipe = _resolved_recipe(spec, inst)
        for nax, nay, ninst, nspec in _adjacent_anchors(state, ax, ay, w, h):
            if str(ninst.get("type") or "") == "storage":
                sig = (ax, ay, nax, nay, "storage")
                if sig not in seen:
                    seen.add(sig)
                    links.append({"x0": ax, "y0": ay, "x1": nax, "y1": nay, "kind": "storage"})
            else:
                nrecipe = _resolved_recipe(nspec, ninst)
                for res in recipe.get("inputs") or {}:
                    if res in (nrecipe.get("outputs") or {}):
                        sig = (nax, nay, ax, ay, "upstream")
                        if sig not in seen:
                            seen.add(sig)
                            links.append({"x0": nax, "y0": nay, "x1": ax, "y1": ay, "kind": "upstream"})
    return links


def _find_zone_slot(state: dict[str, Any], zone: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int] | None:
    x0, y0, x1, y1 = zone
    for y in range(y0, max(y0, y1 - h + 1)):
        for x in range(x0, max(x0, x1 - w + 1)):
            if _cells_free(state, x, y, w, h):
                return x, y
    return None


def _devices_of_type(state: dict[str, Any], dtype: str) -> list[tuple[str, dict[str, Any]]]:
    return [(k, v) for k, v in state["cells"].items() if str(v.get("type") or "") == dtype]


def _delegation_active_targets(state: dict[str, Any]) -> dict[str, int]:
    targets: dict[str, int] = {}
    wh = state["warehouse"]
    for contract in state.get("active_contracts") or []:
        if not isinstance(contract, dict):
            continue
        for k, v in (contract.get("need") or {}).items():
            deficit = max(0, int(v) - int(wh.get(k, 0)))
            if deficit > 0:
                targets[k] = max(targets.get(k, 0), deficit)
    if not targets:
        targets["parts"] = max(0, 8 - int(wh.get("parts", 0)))
    return targets


def _best_npc_for_device(dtype: str, assigned: dict[str, int], *, resting: frozenset[str] | None = None) -> str:
    """为指定设备类型选择最合适的 NPC（允许每个 NPC 管理多台设备，上限 MAX_NPC_ASSIGNMENTS）。"""
    best = ""
    best_score = -1.0
    for nid, prof in NPC_PROFILES.items():
        if nid == "temp_worker":
            continue
        if nid in assigned and assigned[nid] >= MAX_NPC_ASSIGNMENTS:
            continue
        if resting and nid in resting:
            continue
        score = 0.0
        if dtype in prof.get("good", frozenset()):
            score = float(prof.get("output_mult", 1.0))
        elif dtype in prof.get("bad_devices", frozenset()):
            score = float(prof.get("bad_output_mult", 0.5)) - 0.3  # 轻微惩罚避免同 NPC 重复分配差设备
        else:
            score = 0.85
        if score > best_score:
            # 已分配的设备数量越少越优先（负载均衡）
            load_penalty = 0.0 if nid not in assigned else assigned[nid] * 0.05
            effective = score - load_penalty
            if effective > best_score:
                best_score = effective
                best = nid
    if not best:
        return ""  # 无可用 NPC
    return best


def _delegation_pass(sess: Any, state: dict[str, Any]) -> None:
    if not state.get("delegation_on") or state.get("abandoned"):
        state["delegation_action_zh"] = ""
        return
    actions: list[str] = []
    targets = _delegation_active_targets(state)
    needed_types: set[str] = set()
    for res in targets:
        for dtype in DELEGATION_DEVICE_CHAIN.get(res, ()):
            needed_types.add(dtype)
    if int(sess.resources.energy) < 30:
        needed_types.update(("power_plant", "miner", "storage"))

    # 一键派遣：自动补建所有缺失的设备类型（每种至少一台）
    built_any = False
    all_dtypes = ("storage", "miner", "smelter", "assembler", "printer", "refiner", "power_plant", "power_core")
    for dtype in all_dtypes:
        if _devices_of_type(state, dtype):
            continue
        spec = DEVICE_CATALOG.get(dtype)
        if not spec:
            continue
        zone = DELEGATION_BUILD_ZONES.get(dtype, (0, 0, GRID_SIZE, GRID_SIZE))
        w, h = int(spec["w"]), int(spec["h"])
        slot = _find_zone_slot(state, zone, w, h)
        if not slot:
            continue
        cost = dict(spec.get("build") or {})
        if any(int(getattr(sess.resources, k, 0)) < int(v) for k, v in cost.items()):
            continue
        sx, sy = slot
        sess.resources.apply(**{k: -int(v) for k, v in cost.items()})
        state["cells"][_cell_key(sx, sy)] = {
            "type": dtype,
            "level": 1,
            "enabled": True,
            "npc_id": "",
            "progress": 0.0,
            "recipe": "default",
        }
        built_any = True
        actions.append(f"自动建造{spec['label_zh']}")

    if "medical_pack" in targets:
        for key, inst in state["cells"].items():
            if str(inst.get("type") or "") == "printer" and not inst.get("recipe_manual"):
                inst["recipe"] = "medical"
    elif "parts" in targets:
        for key, inst in state["cells"].items():
            if str(inst.get("type") or "") == "printer" and not inst.get("recipe_manual"):
                inst["recipe"] = "default"

    assigned: dict[str, int] = {}
    resting_ids = frozenset(str(s) for s in (state.get("npc_resting_ids") or []) if s and s.strip())
    for key, inst in sorted(state["cells"].items()):
        dtype = str(inst.get("type") or "")
        if dtype == "storage":
            continue
        inst["enabled"] = True
        if not str(inst.get("npc_id") or "").strip():
            pick = _best_npc_for_device(dtype, assigned, resting=resting_ids)
            if pick:
                inst["npc_id"] = pick
                assigned[pick] = assigned.get(pick, 0) + 1
                actions.append(f"委任{NPC_PROFILES[pick]['label_zh']}→{DEVICE_CATALOG[dtype]['label_zh']}")
            else:
                # 无可用 NPC，设备保持空闲（不再使用临时帮工）
                inst["npc_id"] = ""

    if built_any:
        _maybe_log_event(state, "委任管理：已自动补建缺失设备类型，每人最多管理 2 台。")
    if actions:
        state["delegation_action_zh"] = "；".join(actions[:6])
    else:
        state["delegation_action_zh"] = "委任管理：已分配人员至全部设备（每人≤2台），效率 70%。"


def set_production_caps(sess: Any, caps: dict[str, Any] | None, enabled: bool | None = None) -> None:
    _auto_tick(sess)
    state = _state(sess)
    if caps is not None:
        state["stop_caps"] = _normalize_stop_caps(caps)
    if enabled is not None:
        state["stop_caps_enabled"] = bool(enabled)
    _save(sess, state)


def _apply_outputs(state: dict[str, Any], outputs: dict[str, float]) -> None:
    wh = state["warehouse"]
    for k, v in outputs.items():
        if k == "base_energy":
            continue
        n = max(0, int(round(float(v))))
        if n:
            wh[k] = int(wh.get(k, 0)) + n


def _consume_inputs(state: dict[str, Any], sess: Any, inputs: dict[str, float]) -> bool:
    wh = state["warehouse"]
    for k, v in inputs.items():
        need = max(0, int(round(float(v))))
        if k == "source_ore":
            if int(state.get("source_ore_buffer", 0)) < need:
                return False
        elif int(wh.get(k, 0)) < need:
            return False
    for k, v in inputs.items():
        need = max(0, int(round(float(v))))
        if k == "source_ore":
            state["source_ore_buffer"] = int(state["source_ore_buffer"]) - need
        else:
            wh[k] = int(wh.get(k, 0)) - need
    return True


def _resolved_recipe(spec: dict[str, Any], inst: dict[str, Any]) -> dict[str, Any]:
    if spec.get("storage_bonus"):
        return {
            "cycle_s": 0.0,
            "energy_per_cycle": 0,
            "inputs": {},
            "outputs": {},
            "accident_rate": 0.0,
        }
    lvl = max(1, int(inst.get("level", 1) or 1))
    recipe = {
        "cycle_s": float(spec.get("cycle_s", 60.0)),
        "energy_per_cycle": int(spec.get("energy_per_cycle", 0)),
        "inputs": dict(spec.get("inputs") or {}),
        "outputs": dict(spec.get("outputs") or {}),
        "accident_rate": float(spec.get("accident_rate", 0.0)),
    }
    if _normalize_printer_recipe(inst.get("recipe")) == "medical" and spec.get("alt_recipe"):
        alt = spec["alt_recipe"]
        recipe["inputs"] = dict(alt.get("inputs") or {})
        recipe["outputs"] = dict(alt.get("outputs") or {})
        recipe["energy_per_cycle"] = int(alt.get("energy_per_cycle", recipe["energy_per_cycle"]))
    if lvl >= 2 and spec.get("upgrade"):
        up = spec["upgrade"]
        if "cycle_s" in up:
            recipe["cycle_s"] = float(up["cycle_s"])
        if "cycle_mult" in up:
            recipe["cycle_s"] *= float(up["cycle_mult"])
        if "energy_per_cycle" in up:
            recipe["energy_per_cycle"] = int(up["energy_per_cycle"])
        if "inputs" in up:
            recipe["inputs"] = dict(up["inputs"])
        if "outputs" in up:
            recipe["outputs"] = dict(up["outputs"])
        if "accident_rate" in up:
            recipe["accident_rate"] = float(up["accident_rate"])
    if PRODUCTION_SPEED_MULT > 1.0:
        recipe["cycle_s"] = max(1.0, float(recipe["cycle_s"]) / PRODUCTION_SPEED_MULT)
    return recipe


def blueprint_available(sess: Any) -> bool:
    if str(getattr(sess, "story_phase", "") or "").strip() == "Sandbox":
        return True
    if sess.plot.has("underground_workshop_built"):
        return True
    if sess.plot.has("workshop_blueprint_hint"):
        return True
    if bool(getattr(sess.hidden, "chubby_quest_complete", False)):
        return True
    completed = frozenset(getattr(sess, "completed_nodes", []) or [])
    if "01-02" in completed:
        return True
    if completed & frozenset({"01-04", "01-07", "PRO-04"}):
        return True
    return False


def grant_blueprint_from_story(sess: Any, bulletin_zh: str, *, silent_if_known: bool = False) -> None:
    if sess.plot.has("workshop_blueprint_hint"):
        return
    sess.plot.enable("workshop_blueprint_hint")
    state = _state(sess)
    if not state["blueprint_known"]:
        state["blueprint_known"] = True
        _maybe_log_event(state, bulletin_zh)
        _save(sess, state)
    if not silent_if_known or not state.get("blueprint_known"):
        append_bulletin_zh(sess, bulletin_zh)


def comm_trade_available(sess: Any) -> bool:
    if sess.plot.has("workshop_comm_trade_unlocked"):
        return True
    completed = frozenset(getattr(sess, "completed_nodes", []) or [])
    if "01-02" in completed:
        return True
    if str(getattr(sess, "current_node_id", "") or "").strip() in {"01-04", "01-07", "02-01", "02-02"}:
        return True
    return str(getattr(sess, "story_phase", "") or "").strip() == "Sandbox"


def _npc_fatigue_mult(npc_id: str, state: dict[str, Any]) -> float:
    nid = str(npc_id or "").strip()
    if not nid or nid == "temp_worker":
        return 1.0
    mins = float((state.get("npc_fatigue_minutes") or {}).get(nid, 0.0) or 0.0)
    if mins <= NPC_FATIGUE_THRESHOLD_MIN:
        return 1.0
    hours_over = (mins - NPC_FATIGUE_THRESHOLD_MIN) / 60.0
    penalty = min(0.5, hours_over * NPC_FATIGUE_PENALTY_PER_HOUR)
    return max(0.5, 1.0 - penalty)


def _accumulate_npc_fatigue(state: dict[str, Any], elapsed_s: float) -> None:
    if elapsed_s <= 0:
        return
    active: set[str] = set()
    for inst in state["cells"].values():
        if not inst.get("enabled", True):
            continue
        nid = str(inst.get("npc_id") or "").strip()
        if nid and nid != "temp_worker":
            active.add(nid)
    if not active:
        return
    bank = dict(state.get("npc_fatigue_minutes") or {})
    add = float(elapsed_s) * GAME_MINUTES_PER_REAL_SECOND
    for nid in active:
        bank[nid] = float(bank.get(nid, 0.0) or 0.0) + add
    state["npc_fatigue_minutes"] = bank


def _npc_mult(inst: dict[str, Any], spec: dict[str, Any], state: dict[str, Any]) -> tuple[float, float]:
    npc_id = str(inst.get("npc_id") or "").strip()
    if not npc_id:
        return 1.0, 0.0
    prof = NPC_PROFILES.get(npc_id)
    if not prof:
        return 1.0, 0.0
    dtype = str(inst.get("type") or "")
    if dtype in prof.get("bad_devices", frozenset()):
        base = float(prof.get("bad_output_mult", 0.8))
    elif dtype in prof.get("good", frozenset()):
        base = float(prof.get("output_mult", 1.0))
    else:
        base = 1.0
    return base * _npc_fatigue_mult(npc_id, state), float(prof.get("accident_delta", 0.0))


def _maybe_log_event(state: dict[str, Any], text: str) -> None:
    if not text:
        return
    log = list(state.get("events_log") or [])
    log.append(text)
    state["events_log"] = log[-20:]


def _cycle_block_reason(
    sess: Any,
    state: dict[str, Any],
    key: str,
    inst: dict[str, Any],
    spec: dict[str, Any],
) -> str | None:
    if not inst.get("enabled", True):
        return "off"
    if spec.get("storage_bonus"):
        return "storage"
    npc_id = str(inst.get("npc_id") or "").strip()
    if not npc_id or npc_id == "temp_worker":
        return "idle"
    ax, ay = _parse_cell_key(key)
    w, h = int(spec["w"]), int(spec["h"])
    recipe = _resolved_recipe(spec, inst)
    prod_outs = {k: float(v) for k, v in recipe["outputs"].items() if k != "base_energy"}
    if _output_blocked_by_cap(state, prod_outs):
        return "cap"
    log_ok, _ = _logistics_ok(state, ax, ay, w, h, recipe)
    if not log_ok:
        return "logistics"
    energy_need = int(recipe.get("energy_per_cycle", 0))
    if energy_need > 0 and sess.resources.energy < energy_need:
        return "energy"
    ok_in, _ = _inputs_available(state, sess, recipe.get("inputs") or {})
    if not ok_in:
        return "materials"
    if prod_outs and not _can_store(state, prod_outs):
        return "full"
    return None


def _can_run_device_cycle(
    sess: Any,
    state: dict[str, Any],
    key: str,
    inst: dict[str, Any],
    spec: dict[str, Any],
) -> bool:
    return _cycle_block_reason(sess, state, key, inst, spec) is None


def _run_device_cycle(
    sess: Any,
    state: dict[str, Any],
    key: str,
    inst: dict[str, Any],
    spec: dict[str, Any],
    eff_mult: float,
) -> bool:
    if _cycle_block_reason(sess, state, key, inst, spec) is not None:
        return False
    ax, ay = _parse_cell_key(key)
    w, h = int(spec["w"]), int(spec["h"])
    recipe = _resolved_recipe(spec, inst)
    out_scaled = {k: float(v) for k, v in recipe["outputs"].items()}
    energy_need = int(recipe.get("energy_per_cycle", 0))
    if not _consume_inputs(state, sess, recipe["inputs"]):
        return False
    npc_out, npc_acc = _npc_mult(inst, spec, state)
    for k in list(out_scaled.keys()):
        if k != "base_energy":
            out_scaled[k] = max(0.0, out_scaled[k] * npc_out * eff_mult)
            # 防止产出因 NPC 低倍率 / 委任效率折损被 round 为 0，
            # 导致设备"运行中"但实际不产出任何资源。
            if out_scaled[k] > 0.0 and int(round(out_scaled[k])) < 1:
                out_scaled[k] = 1.0
    if not _can_store(state, {k: v for k, v in out_scaled.items() if k != "base_energy"}):
        return False

    accident_rate = float(recipe.get("accident_rate", 0.0)) + npc_acc
    npc_id = str(inst.get("npc_id") or "").strip()
    if accident_rate > 0 and random.random() < accident_rate:
        _maybe_log_event(state, f"{spec['label_zh']}发生事故，本周期产出作废。")
        if energy_need > 0:
            sess.resources.energy = max(0, sess.resources.energy - energy_need)
        prof = NPC_PROFILES.get(npc_id)
        if prof and prof.get("event_zh") and random.random() < float(prof.get("event_rate", 0.05)):
            _maybe_log_event(state, str(prof["event_zh"]))
            if npc_id == "dr_lin" and random.random() < 0.35:
                st = sess.get_memory_store("dr_lin")
                st.emotional.trust = max(0.0, st.emotional.trust - 3.0)
                sess.save_memory_store(st)
        return True

    if energy_need > 0:
        sess.resources.energy = max(0, sess.resources.energy - energy_need)
    _apply_outputs(state, out_scaled)
    if "base_energy" in out_scaled:
        gain = max(0, int(round(float(out_scaled["base_energy"]) * npc_out * eff_mult)))
        sess.resources.energy += gain
        _maybe_log_event(state, f"{spec['label_zh']}出力完成，基地能源 +{gain}。")
    inst["progress"] = float(inst.get("progress", 0.0) or 0.0)
    state["total_cycles"] = int(state.get("total_cycles", 0)) + 1

    prof = NPC_PROFILES.get(npc_id)
    if prof and prof.get("event_zh") and random.random() < float(prof.get("event_rate", 0.05)) * 0.35:
        _maybe_log_event(state, str(prof["event_zh"]))
    return True


def tick_workshop(sess: Any, elapsed_s: float) -> None:
    state = _state(sess)
    if not state["built"] or state.get("abandoned") or elapsed_s <= 0:
        _save(sess, state)
        return

    if state.get("delegation_on"):
        _delegation_pass(sess, state)

    eff = DELEGATION_EFFICIENCY if state["delegation_on"] else 1.0
    remaining = float(elapsed_s)
    _accumulate_npc_fatigue(state, elapsed_s)

    anchors = sorted(
        state["cells"].items(),
        key=lambda kv: (DEVICE_CATALOG.get(str(kv[1].get("type")), {}).get("label_zh", ""), kv[0]),
    )

    while remaining > 0.01:
        step = min(remaining, 1.0)
        any_progress = False
        for key, inst in anchors:
            spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
            if not spec or spec.get("storage_bonus"):
                continue
            if not _can_run_device_cycle(sess, state, key, inst, spec):
                continue
            recipe = _resolved_recipe(spec, inst)
            cycle_s = max(1.0, float(recipe["cycle_s"]))
            inst["progress"] = float(inst.get("progress", 0.0) or 0.0) + step * eff
            while inst["progress"] >= cycle_s:
                inst["progress"] -= cycle_s
                if not _run_device_cycle(sess, state, key, inst, spec, eff):
                    inst["progress"] = min(inst["progress"], cycle_s - 0.01)
                    break
                any_progress = True
            if any_progress:
                pass
        remaining -= step
        if not anchors:
            break

    state["last_tick_ts"] = time.time()
    _save(sess, state)


def _auto_tick(sess: Any) -> None:
    state = _state(sess)
    if not state["built"]:
        _save(sess, state)
        return
    now = time.time()
    last = float(state.get("last_tick_ts") or 0.0)
    if last <= 0:
        state["last_tick_ts"] = now
        _save(sess, state)
        return
    elapsed = min(MAX_TICK_S, max(0.0, now - last))
    if elapsed > 0.05:
        tick_workshop(sess, elapsed)
    else:
        state["last_tick_ts"] = now
        _save(sess, state)


def workshop_daily_pass(sess: Any) -> None:
    state = _state(sess)
    if not state["built"]:
        return
    cycles_before = int(state.get("total_cycles", 0) or 0)
    energy_before = int(sess.resources.energy)

    # 统计每个 NPC 管理的设备及其岗位评价
    assigned_npc_ids: set[str] = set()
    npc_devices: dict[str, list[dict[str, Any]]] = {}  # nid → [{"type":..., "good":..., "bad":...}, ...]
    for inst in state["cells"].values():
        nid = str(inst.get("npc_id") or "").strip()
        if not nid or nid == "temp_worker" or not inst.get("enabled", True):
            continue
        assigned_npc_ids.add(nid)
        dtype = str(inst.get("type") or "")
        prof = NPC_PROFILES.get(nid)
        if not prof:
            continue
        npc_devices.setdefault(nid, []).append({
            "type": dtype,
            "label": DEVICE_CATALOG.get(dtype, {}).get("label_zh", dtype),
            "good": dtype in prof.get("good", frozenset()),
            "bad": dtype in prof.get("bad_devices", frozenset()),
        })

    food_cost = sum(1 for _ in assigned_npc_ids)
    if food_cost > 0:
        sess.resources.food = max(0, int(sess.resources.food) - food_cost)
        if food_cost >= 2:
            _maybe_log_event(state, f"设施轮班消耗补给 ×{food_cost}。")

    # ---------- NPC 记忆更新：根据工作岗位影响信任/好感 ----------
    for nid, devices in npc_devices.items():
        try:
            st = sess.get_memory_store(nid)
            prof = NPC_PROFILES.get(nid)
            label = prof["label_zh"] if prof else nid
            good_count = sum(1 for d in devices if d["good"])
            bad_count = sum(1 for d in devices if d["bad"])
            neutral_count = len(devices) - good_count - bad_count
            total = len(devices)

            trust_delta = 0.0
            affinity_delta = 0.0
            notes: list[str] = []

            if good_count > 0:
                trust_delta += min(good_count * 0.8, 2.0)
                affinity_delta += min(good_count * 1.0, 2.0)
                good_labels = [d["label"] for d in devices if d["good"]]
                notes.append(f"被委任到擅长的岗位：{'、'.join(good_labels)}")
            if bad_count > 0:
                trust_delta -= min(bad_count * 0.6, 1.5)
                affinity_delta -= min(bad_count * 1.0, 2.0)
                bad_labels = [d["label"] for d in devices if d["bad"]]
                notes.append(f"被分配到不擅长的岗位：{'、'.join(bad_labels)}，感觉被刁难")
            if neutral_count > 0 and good_count == 0 and bad_count == 0:
                affinity_delta += 0.3  # 至少有事做，微小正面
            if total >= MAX_NPC_ASSIGNMENTS:
                fear_delta = 0.5  # 多设备管理压力
                st.emotional.fear = min(100.0, st.emotional.fear + fear_delta)

            st.emotional.trust = max(0.0, min(100.0, st.emotional.trust + trust_delta))
            st.emotional.affinity = max(0.0, min(100.0, st.emotional.affinity + affinity_delta))

            if notes:
                day_label = f"第{sess.day}日 基地核心轮班"
                st.long_term_notes.append(f"{day_label}：{label}管理{total}台设备。{'；'.join(notes)}")
                if len(st.long_term_notes) > 30:
                    st.long_term_notes = st.long_term_notes[-30:]

            sess.save_memory_store(st)
        except Exception:
            pass

    # ---------- 疲劳惩罚 ----------
    bank = dict(state.get("npc_fatigue_minutes") or {})
    for nid, mins in bank.items():
        if nid == "temp_worker" or float(mins or 0) <= NPC_FATIGUE_THRESHOLD_MIN:
            continue
        try:
            st = sess.get_memory_store(nid)
            st.emotional.trust = max(0.0, st.emotional.trust - NPC_FATIGUE_TRUST_DRAIN)
            st.emotional.fear = min(100.0, st.emotional.fear + 0.5)
            sess.save_memory_store(st)
        except Exception:
            pass

    if not state.get("abandoned"):
        tick_workshop(sess, DAILY_PASS_S)

    state = _state(sess)
    cycles_after = int(state.get("total_cycles", 0) or 0)
    starved = int(sess.resources.energy) <= 0 and cycles_after == cycles_before and energy_before <= 2
    if starved and not state.get("abandoned"):
        state["energy_deficit_days"] = int(state.get("energy_deficit_days", 0) or 0) + 1
        if state["energy_deficit_days"] >= ABANDON_DEFICIT_DAYS:
            state["abandoned"] = True
            _maybe_log_event(state, "长期能源赤字：自动化设施进入废弃状态，需投入资源重新启动。")
            append_bulletin_zh(
                sess,
                f"基地核心自动化设施因连续 {ABANDON_DEFICIT_DAYS} 日能源枯竭而停摆——可在基地核心支付重启成本恢复运营。",
            )
    elif not state.get("abandoned"):
        state["energy_deficit_days"] = 0

    if not state.get("abandoned") and _ensure_active_contracts(sess, state):
        _maybe_log_event(state, "调度台发布了新的生产指标。")

    state["last_day_cycles"] = cycles_after
    _save(sess, state)


def discover_blueprint(sess: Any) -> tuple[bool, str | None]:
    state = _state(sess)
    if state["blueprint_known"]:
        return True, None
    if not blueprint_available(sess):
        return False, "尚未获得自动化设施蓝图。推进第一幕（完成基地升级相关节点）或完成小胖相关任务后再来。"
    state["blueprint_known"] = True
    sess.plot.enable("workshop_blueprint_hint")
    _maybe_log_event(state, "小胖提到：基地核心中有一处闲置空间，也许能改造成自动化产线。")
    _save(sess, state)
    append_bulletin_zh(sess, "获得基地核心自动化设施蓝图：可在基地核心中改造生产空间。")
    return True, None


def _deduct_build_cost(sess: Any, state: dict[str, Any], cost: dict[str, Any], action_label: str = "建造") -> tuple[bool, str | None]:
    """扣除建造/升级/改造的资源消耗。零件部分：基地资源不足时自动从工坊仓库转运。

    采用两阶段模式：先验证全部资源是否充足，再执行修改，避免失败时污染 sess.resources。
    """
    wh = state.get("warehouse") or {}
    # 阶段一：仅计算，不修改任何持久化对象
    needed_from_wh: dict[str, int] = {}  # k → 需从仓库转运的数量
    final_cost: dict[str, int] = {}
    for k, v in cost.items():
        need = int(v)
        base_have = int(getattr(sess.resources, k, 0))
        if k == "parts" and base_have < need:
            wh_have = int(wh.get("parts", 0) or 0)
            shortfall = need - base_have
            if wh_have < shortfall:
                label = _RESOURCE_ZH.get(k, k)
                return False, f"{action_label}资源不足（需要{label} {need}，基地{base_have}，仓库{wh_have}）。"
            needed_from_wh[k] = shortfall
            base_have += shortfall
        if base_have < need:
            label = _RESOURCE_ZH.get(k, k)
            return False, f"{action_label}资源不足（需要{label} {need}）。"
        final_cost[k] = -need

    # 阶段二：执行修改（此时已确保全部校验通过）
    for k, take in needed_from_wh.items():
        wh[k] = int(wh.get(k, 0) or 0) - take
        setattr(sess.resources, k, int(getattr(sess.resources, k, 0)) + take)
    sess.resources.apply(**final_cost)
    return True, None


def construct_workshop(sess: Any) -> tuple[bool, str | None]:
    ok, err = discover_blueprint(sess)
    if not ok:
        return False, err
    ensure_workshop_entry_resources(sess)
    state = _state(sess)
    if state["built"]:
        workshop_entry_pass(sess)
        return True, None
    ok, err = _deduct_build_cost(sess, state, BUILD_SITE_COST, "改造")
    if not ok:
        return False, err
    state["built"] = True
    state["last_tick_ts"] = time.time()
    placed = _place_starter_devices(state)
    if placed:
        _maybe_log_event(state, f"改造完成并配装：{'、'.join(placed)}。")
    else:
        _maybe_log_event(state, "基地核心自动化设施改造完成：10×10 网格已就绪，可放置设备开始自动化生产。")
    if _ensure_active_contracts(sess, state):
        _maybe_log_event(state, "调度台发布了首批生产指标。")
    sess.plot.enable("underground_workshop_built")
    _save(sess, state)
    msg = "基地核心自动化设施已启用：能源 30 + 零件 15 改造完成。"
    if placed:
        msg += f" 启动配装：{'、'.join(placed)}。"
    msg += " 下一步：放置 3D 打印机（能源 30 + 零件 15）；能源吃紧时在能源区建发电站（1 矿石 → 基地能源）。"
    append_bulletin_zh(sess, msg)
    return True, None


def _cells_free(state: dict[str, Any], x: int, y: int, w: int, h: int) -> bool:
    if x < 0 or y < 0 or x + w > GRID_SIZE or y + h > GRID_SIZE:
        return False
    for dy in range(h):
        for dx in range(w):
            if _device_at(state, x + dx, y + dy):
                return False
    return True


def _cells_free_except(
    state: dict[str, Any],
    x: int,
    y: int,
    w: int,
    h: int,
    exclude_key: str,
) -> bool:
    if x < 0 or y < 0 or x + w > GRID_SIZE or y + h > GRID_SIZE:
        return False
    ex_ax, ex_ay = _parse_cell_key(exclude_key)
    ex_spec = DEVICE_CATALOG.get(str((state["cells"].get(exclude_key) or {}).get("type") or ""))
    ex_w = int(ex_spec["w"]) if ex_spec else 1
    ex_h = int(ex_spec["h"]) if ex_spec else 1
    for dy in range(h):
        for dx in range(w):
            cx, cy = x + dx, y + dy
            if ex_ax <= cx < ex_ax + ex_w and ex_ay <= cy < ex_ay + ex_h:
                continue
            if _device_at(state, cx, cy):
                return False
    return True


def build_device(sess: Any, x: int, y: int, device_type: str) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    if not state["built"]:
        return False, "请先完成设施改造。"
    if state.get("abandoned"):
        return False, "设施已废弃，请先重启后再建造设备。"
    spec = DEVICE_CATALOG.get(str(device_type or "").strip())
    if not spec:
        return False, "未知设备类型。"
    w, h = int(spec["w"]), int(spec["h"])
    if not _cells_free(state, x, y, w, h):
        return False, "该区域无法放置（越界或已被占用）。"
    cost = dict(spec.get("build") or {})
    ok, err = _deduct_build_cost(sess, state, cost, "建造")
    if not ok:
        return False, err
    state["cells"][_cell_key(x, y)] = {
        "type": device_type,
        "level": 1,
        "enabled": True,
        "npc_id": "",
        "progress": 0.0,
        "recipe": "default",
    }
    _save(sess, state)
    return True, None


def upgrade_device(sess: Any, x: int, y: int) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    hit = _device_at(state, x, y)
    if not hit:
        return False, "此处没有设备。"
    key, inst = hit
    if _parse_cell_key(key) != (x, y):
        return False, "请点击设备左上角格子进行升级。"
    spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
    if not spec or not spec.get("upgrade"):
        return False, "该设备不可升级。"
    if int(inst.get("level", 1)) >= 2:
        return False, "已达最高等级。"
    cost = dict(spec["upgrade"].get("cost") or {})
    ok, err = _deduct_build_cost(sess, state, cost, "升级")
    if not ok:
        return False, err
    inst["level"] = 2
    _save(sess, state)
    return True, None


def demolish_device(sess: Any, x: int, y: int) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    hit = _device_at(state, x, y)
    if not hit:
        return False, "此处没有设备。"
    key, _inst = hit
    if _parse_cell_key(key) != (x, y):
        return False, "请点击设备左上角格子进行拆除。"
    del state["cells"][key]
    _save(sess, state)
    return True, None


def move_device(sess: Any, from_x: int, from_y: int, to_x: int, to_y: int) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    if not state["built"]:
        return False, "请先完成设施改造。"
    if state.get("abandoned"):
        return False, "设施已废弃，请先重启后再移动设备。"
    hit = _device_at(state, from_x, from_y)
    if not hit:
        return False, "此处没有设备。"
    key, inst = hit
    if _parse_cell_key(key) != (from_x, from_y):
        return False, "请点击设备左上角格子开始移动。"
    if (from_x, from_y) == (to_x, to_y):
        return False, "设备已在该位置。"
    spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
    if not spec:
        return False, "未知设备类型。"
    w, h = int(spec["w"]), int(spec["h"])
    if not _cells_free_except(state, to_x, to_y, w, h, key):
        return False, "目标区域无法放置（越界或已被占用）。"
    del state["cells"][key]
    state["cells"][_cell_key(to_x, to_y)] = inst
    _save(sess, state)
    return True, None


def toggle_device(sess: Any, x: int, y: int) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    hit = _device_at(state, x, y)
    if not hit:
        return False, "此处没有设备。"
    _key, inst = hit
    inst["enabled"] = not bool(inst.get("enabled", True))
    _save(sess, state)
    return True, None


def set_device_recipe(sess: Any, x: int, y: int, recipe: str) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    hit = _device_at(state, x, y)
    if not hit:
        return False, "此处没有设备。"
    key, inst = hit
    if _parse_cell_key(key) != (x, y):
        return False, "请点击设备左上角格子。"
    if str(inst.get("type")) != "printer":
        return False, "仅 3D 打印机可切换配方。"
    next_recipe = _normalize_printer_recipe(recipe)
    prev_recipe = _normalize_printer_recipe(inst.get("recipe"))
    inst["recipe"] = next_recipe
    inst["recipe_manual"] = True
    if next_recipe != prev_recipe:
        inst["progress"] = 0.0
    _save(sess, state)
    return True, None


def assign_npc(sess: Any, x: int, y: int, npc_id: str) -> tuple[bool, str | None]:
    """手动分配 NPC 到指定设备。

    NOTE: 此处不调用 _auto_tick()，因为若委任管理开启，tick_workshop()
    会触发 _delegation_pass()，导致所有空设备被自动补 NPC——与"手动只分配
    一台"的预期矛盾。生产推进在上一次 UI 刷新 / 下次进入时自然会补齐。
    """
    state = _state(sess)
    hit = _device_at(state, x, y)
    if not hit:
        return False, "此处没有设备。"
    key, inst = hit
    if _parse_cell_key(key) != (x, y):
        return False, "请点击设备左上角格子分配 NPC。"
    nid = str(npc_id or "").strip()
    if nid and nid not in NPC_PROFILES:
        return False, "未知 NPC。"
    if nid == "temp_worker":
        return False, "临时帮工已移除，请派遣正式人员。"
    # 检查该 NPC 是否已达最大管理设备数（排除当前设备自身）
    current_device_count = sum(
        1 for k, v in state["cells"].items()
        if str(v.get("npc_id") or "").strip() == nid and (k != key)
    )
    if nid and current_device_count >= MAX_NPC_ASSIGNMENTS:
        label = NPC_PROFILES[nid]["label_zh"]
        return False, f"{label} 已管理 {MAX_NPC_ASSIGNMENTS} 台设备，无法再分配。"
    inst["npc_id"] = nid
    # 手动分配后清除该 NPC 的休息标记
    resting = list(state.get("npc_resting_ids") or [])
    if nid in resting:
        resting.remove(nid)
        state["npc_resting_ids"] = resting
    _save(sess, state)
    return True, None


def set_delegation(sess: Any, enabled: bool) -> None:
    _auto_tick(sess)
    state = _state(sess)
    state["delegation_on"] = bool(enabled)
    # 切换委任模式时清除手动休息标记，让 NPC 恢复可分配状态
    state["npc_resting_ids"] = []
    if state["delegation_on"]:
        _delegation_pass(sess, state)
    else:
        state["delegation_action_zh"] = ""
    _save(sess, state)


def import_source_ore(sess: Any, amount: int = 1) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    if not state["built"]:
        return False, "设施尚未启用。"
    n = max(1, min(5, int(amount)))
    cost = 8 * n
    if sess.resources.energy < cost:
        return False, f"导入源矿需要能源 {cost}。"
    if int(state["source_ore_buffer"]) + n > 20:
        return False, "源矿缓冲已满（上限 20）。"
    sess.resources.energy = max(0, sess.resources.energy - cost)
    state["source_ore_buffer"] = int(state["source_ore_buffer"]) + n
    _save(sess, state)
    return True, None


def export_to_base(sess: Any, resource: str, amount: int) -> tuple[bool, str | None, dict[str, int]]:
    _auto_tick(sess)
    state = _state(sess)
    key = str(resource or "").strip()
    n = max(1, int(amount))
    wh = state["warehouse"]
    if key == "parts":
        have = int(wh.get("parts", 0) or 0)
        if have <= 0:
            return False, "设施零件不足。", {}
        take = min(n, have)
        wh["parts"] = have - take
        sess.resources.parts = int(getattr(sess.resources, "parts", 0)) + take
        _save(sess, state)
        return True, None, {"parts": take}
    if key == "medical_pack":
        have = int(wh.get("medical_pack", 0) or 0)
        if have <= 0:
            return False, "工坊医疗包不足。", {}
        take = min(n, have)
        wh["medical_pack"] = have - take
        sess.resources.medical += take
        _save(sess, state)
        return True, None, {"medical": take}
    return False, "仅可运回零件或医疗包至基地。", {}


def deliver_task(sess: Any, task_id: str) -> tuple[bool, str | None, dict[str, Any]]:
    _auto_tick(sess)
    state = _state(sess)
    tid = str(task_id or "").strip()
    active = list(state.get("active_contracts") or [])
    contract = next((c for c in active if isinstance(c, dict) and str(c.get("id") or "") == tid), None)
    if not contract:
        return False, "未知生产指标。", {}
    need = dict(contract.get("need") or {})
    wh = state["warehouse"]
    for k, v in need.items():
        label = RES_ZH.get(k, k)
        if int(wh.get(k, 0)) < int(v):
            return False, f"物资不足：还需 {label} ×{int(v) - int(wh.get(k, 0))}。", {}
    for k, v in need.items():
        wh[k] = int(wh.get(k, 0)) - int(v)
    granted = _grant_contract_rewards(sess, state, contract)
    reveal_zh = _apply_hidden_branch(sess, contract)
    reward_zh = _format_resources_zh(granted)
    completed = dict(contract)
    completed["completed_ts"] = time.time()
    completed.pop("hidden_branch", None)
    history = list(state.get("completed_contracts") or [])
    history.append(completed)
    state["completed_contracts"] = history[-MAX_COMPLETED_CONTRACT_HISTORY:]
    state["active_contracts"] = [c for c in active if str(c.get("id") or "") != tid]
    _maybe_log_event(state, f"指标达成：{contract.get('issuer_zh', '委托')}。")
    if reveal_zh:
        _maybe_log_event(state, reveal_zh)
    if _ensure_active_contracts(sess, state, force_one=True):
        _maybe_log_event(state, "调度台发布了新的生产指标。")
    _save(sess, state)
    bulletin = f"基地核心指标达成（{contract.get('issuer_zh', '委托')}）— 获得 {reward_zh}"
    if reveal_zh:
        bulletin += f" {reveal_zh}"
    append_bulletin_zh(sess, bulletin)
    return True, None, {"reward_zh": reward_zh, "reveal_zh": reveal_zh, "issuer_zh": contract.get("issuer_zh", "委托")}


def _apply_task_rewards(sess: Any, task_id: str) -> None:
    """兼容旧调用；随机指标奖励已在 deliver_task 中处理。"""
    return


def rest_npc(sess: Any, npc_id: str) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    nid = str(npc_id or "").strip()
    if not nid or nid not in NPC_PROFILES or nid == "temp_worker":
        return False, "无法安排该人员休息。"
    # 1) 清零疲劳
    bank = dict(state.get("npc_fatigue_minutes") or {})
    bank[nid] = 0.0
    state["npc_fatigue_minutes"] = bank
    # 2) 从当前委派的设备上撤下，否则下一 tick 疲劳会立即重新累积
    freed_devices: list[str] = []
    for key, inst in state["cells"].items():
        if str(inst.get("npc_id") or "") == nid:
            inst["npc_id"] = ""
            spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
            if spec:
                freed_devices.append(spec.get("label_zh", str(inst.get("type"))))
    # 3) 标记为"手动休息中"——委任管理的自动分配将跳过该 NPC
    if bool(state.get("delegation_on")):
        resting = list(state.get("npc_resting_ids") or [])
        if nid not in resting:
            resting.append(nid)
        state["npc_resting_ids"] = resting

    evt = f"{NPC_PROFILES[nid]['label_zh']}已强制休息，疲劳清零"
    if freed_devices:
        evt += f"（已从 {'、'.join(freed_devices)} 撤下）"
    if bool(state.get("delegation_on")):
        evt += "；委任模式下将暂不自动分配，关闭并重开委任可恢复自动分配。"
    _maybe_log_event(state, evt)

    # NPC 记忆：被安排休息会提升好感度，减轻工作压力
    try:
        st = sess.get_memory_store(nid)
        label = NPC_PROFILES[nid]["label_zh"]
        st.emotional.affinity = min(100.0, st.emotional.affinity + 2.0)
        st.emotional.fear = max(0.0, st.emotional.fear - 1.0)
        st.long_term_notes.append(f"第{sess.day}日：被{label}安排休息，恢复了精力。")
        if len(st.long_term_notes) > 30:
            st.long_term_notes = st.long_term_notes[-30:]
        sess.save_memory_store(st)
    except Exception:
        pass

    _save(sess, state)
    return True, None


def rehabilitate_workshop(sess: Any) -> tuple[bool, str | None]:
    _auto_tick(sess)
    state = _state(sess)
    if not state["built"]:
        return False, "设施尚未建立。"
    if not state.get("abandoned"):
        return False, "设施仍在运转，无需重启。"
    for k, v in REHAB_COST.items():
        if int(getattr(sess.resources, k, 0)) < int(v):
            label = {"energy": "能源", "parts": "零件"}.get(k, k)
            return False, f"重启需要 {label} {v}。"
    sess.resources.apply(**{k: -int(v) for k, v in REHAB_COST.items()})
    state["abandoned"] = False
    state["energy_deficit_days"] = 0
    _maybe_log_event(state, "工坊已完成重启：设备可重新接入电网。")
    _save(sess, state)
    append_bulletin_zh(sess, "基地核心自动化设施已重新启动。")
    return True, None


def execute_trade(sess: Any, trade_id: str) -> tuple[bool, str | None, dict[str, int]]:
    _auto_tick(sess)
    state = _state(sess)
    if not state["built"] or state.get("abandoned"):
        return False, "设施未在运营，无法交易。", {}
    if not comm_trade_available(sess):
        return False, "通讯阵列尚未就绪，无法通过频道交换工业资源。", {}
    tid = str(trade_id or "").strip()
    offer = next((o for o in TRADE_OFFERS if o["id"] == tid), None)
    if not offer:
        return False, "未知交易项。", {}
    wh = state["warehouse"]
    for k, v in (offer.get("give") or {}).items():
        if int(wh.get(k, 0)) < int(v):
            return False, f"仓库 {k} 不足。", {}
    payout: dict[str, int] = {}
    for k, v in (offer.get("give") or {}).items():
        wh[k] = int(wh.get(k, 0)) - int(v)
    for k, v in (offer.get("receive") or {}).items():
        if k in INDUSTRIAL_KEYS:
            wh[k] = int(wh.get(k, 0)) + int(v)
            payout[k] = int(v)
        else:
            cur = int(getattr(sess.resources, k, 0))
            setattr(sess.resources, k, cur + int(v))
            payout[k] = int(v)
    _maybe_log_event(state, f"通讯阵列交易：{offer['label_zh']}。")
    _save(sess, state)
    return True, None, payout


_RESOURCE_ZH = {"energy": "能源", "parts": "零件"}


def _afford_cost(sess: Any, cost: dict[str, Any]) -> bool:
    for k, v in cost.items():
        if int(getattr(sess.resources, k, 0)) < int(v):
            return False
    return True


def _upgrade_ui_fields(spec: dict[str, Any], inst: dict[str, Any], sess: Any) -> dict[str, Any]:
    lvl = max(1, int(inst.get("level", 1) or 1))
    up = spec.get("upgrade") or {}
    cost = dict(up.get("cost") or {})
    eligible = bool(up) and lvl < 2
    return {
        "can_upgrade": eligible,
        "upgrade_cost": cost,
        "can_afford_upgrade": eligible and _afford_cost(sess, cost),
    }


def _device_ui(
    inst: dict[str, Any],
    spec: dict[str, Any],
    state: dict[str, Any],
    sess: Any,
    key: str,
) -> dict[str, Any]:
    ax, ay = _parse_cell_key(key)
    npc_id = str(inst.get("npc_id") or "")
    prof = NPC_PROFILES.get(npc_id)
    if spec.get("storage_bonus"):
        lvl = max(1, int(inst.get("level", 1) or 1))
        bonus = int(spec["storage_bonus"])
        if lvl >= 2 and spec.get("upgrade", {}).get("storage_bonus"):
            bonus = int(spec["upgrade"]["storage_bonus"])
        return {
            "type": inst.get("type"),
            "label_zh": spec.get("label_zh"),
            "level": lvl,
            "enabled": bool(inst.get("enabled", True)),
            "npc_id": npc_id,
            "npc_label_zh": prof["label_zh"] if prof else "",
            "progress": 0.0,
            "cycle_s": 0.0,
            "progress_pct": 0.0,
            "npc_fatigue_minutes": 0.0,
            "npc_efficiency_pct": 100,
            "recipe": "default",
            "w": spec["w"],
            "h": spec["h"],
            **_upgrade_ui_fields(spec, inst, sess),
            "rate_zh": f"仓储+{bonus}",
            "status_code": "storage",
            "status_zh": "仓储扩展",
            "missing_inputs": [],
            "anchor_x": ax,
            "anchor_y": ay,
        }
    recipe = _resolved_recipe(spec, inst)
    npc_id = str(inst.get("npc_id") or "")
    prof = NPC_PROFILES.get(npc_id)
    cycle_s = max(1.0, float(recipe["cycle_s"]))
    progress = float(inst.get("progress", 0.0) or 0.0)
    fatigue_m = float((state.get("npc_fatigue_minutes") or {}).get(npc_id, 0.0) or 0.0) if npc_id else 0.0
    status = _evaluate_device_status(sess, state, key, inst, spec)
    dtype = str(inst.get("type") or "")
    out: dict[str, Any] = {
        "type": inst.get("type"),
        "label_zh": spec.get("label_zh"),
        "level": int(inst.get("level", 1)),
        "enabled": bool(inst.get("enabled", True)),
        "npc_id": npc_id,
        "npc_label_zh": prof["label_zh"] if prof else "",
        "progress": round(progress, 2),
        "cycle_s": cycle_s,
        "progress_pct": round(min(100.0, progress / cycle_s * 100.0), 1),
        "npc_fatigue_minutes": round(fatigue_m, 0),
        "npc_efficiency_pct": round(_npc_fatigue_mult(npc_id, state) * 100, 0) if npc_id else 100,
        "recipe": _normalize_printer_recipe(inst.get("recipe")) if dtype == "printer" else inst.get("recipe", "default"),
        "w": spec["w"],
        "h": spec["h"],
        **_upgrade_ui_fields(spec, inst, sess),
        "rate_zh": _device_rate_zh(spec, inst),
        "status_code": status["code"],
        "status_zh": status["label_zh"],
        "missing_inputs": status.get("missing") or [],
        "anchor_x": ax,
        "anchor_y": ay,
    }
    if dtype == "printer":
        out["recipe_zh"] = _printer_recipe_zh(inst.get("recipe"))
        out["recipe_manual"] = bool(inst.get("recipe_manual", False))
    return out


def build_workshop_snapshot(sess: Any) -> dict[str, Any]:
    _auto_tick(sess)
    state = _state(sess)
    cap = _storage_cap(state)
    wh = state["warehouse"]

    grid: list[list[dict[str, Any] | None]] = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    devices: list[dict[str, Any]] = []
    for key, inst in state["cells"].items():
        ax, ay = _parse_cell_key(key)
        spec = DEVICE_CATALOG.get(str(inst.get("type") or ""))
        if not spec:
            continue
        ui = _device_ui(inst, spec, state, sess, key)
        ui["anchor_x"] = ax
        ui["anchor_y"] = ay
        devices.append(ui)
        w, h = int(spec["w"]), int(spec["h"])
        for dy in range(h):
            for dx in range(w):
                cell = {
                    "anchor_x": ax,
                    "anchor_y": ay,
                    "is_anchor": dx == 0 and dy == 0,
                    **ui,
                }
                grid[ay + dy][ax + dx] = cell

    build_catalog = []
    for dtype, spec in DEVICE_CATALOG.items():
        build_catalog.append(
            {
                "type": dtype,
                "label_zh": spec["label_zh"],
                "w": spec["w"],
                "h": spec["h"],
                "build": spec.get("build") or {},
                "build_cost_zh": _build_cost_zh(spec.get("build") or {}),
                "summary_zh": _device_summary(spec),
            }
        )

    tasks_ui = []
    if state["built"]:
        if _ensure_active_contracts(sess, state):
            _save(sess, state)
        tasks_ui = _build_tasks_ui(sess, state)

    sandbox = str(getattr(sess, "story_phase", "") or "").strip() == "Sandbox"
    inactive = ""
    if not sandbox:
        sp = str(getattr(sess, "story_phase", "") or "").strip() or "StoryBeat"
        inactive = f"设施产线调度建议在「静默运营」期进行（当前：{sp}）；仍可使用设备与交付生产指标。"

    trade_ui = []
    for offer in TRADE_OFFERS:
        can = comm_trade_available(sess)
        trade_ui.append({**offer, "available": can})

    fatigue_ui = []
    resting_ids = frozenset(str(s) for s in (state.get("npc_resting_ids") or []) if s and s.strip())
    # 收集当前正在设备上工作的 NPC
    working_npc_ids: set[str] = set()
    for inst in state["cells"].values():
        nid = str(inst.get("npc_id") or "").strip()
        if nid and nid != "temp_worker":
            working_npc_ids.add(nid)
    for nid, prof in NPC_PROFILES.items():
        if nid == "temp_worker":
            continue
        mins = float((state.get("npc_fatigue_minutes") or {}).get(nid, 0.0) or 0.0)
        # 只有正在设备上工作的 NPC 才会"需要休息"
        is_working = nid in working_npc_ids
        fatigue_ui.append(
            {
                "id": nid,
                "label_zh": prof["label_zh"],
                "fatigue_minutes": round(mins, 0),
                "efficiency_pct": round(_npc_fatigue_mult(nid, state) * 100, 0),
                "needs_rest": is_working and mins > NPC_FATIGUE_THRESHOLD_MIN,
                "is_resting": nid in resting_ids,
                "is_working": is_working,
            }
        )

    return {
        "poi_id": POI_ID,
        "map_pois": list(WORKSHOP_MAP_POIS),
        "world_x": POI_WORLD_X,
        "world_y": POI_WORLD_Y,
        "name_zh": "基地核心",
        "lead_zh": "自动化产线、NPC 岗位与随机生产指标。完成指标获得建造资源；部分指标可能触发未知支线。10×10 网格分区布局，通过基地核心设施进入。",
        "grid_size": GRID_SIZE,
        "zones": [dict(z) for z in WORKSHOP_ZONES],
        "logistics_links": _compute_logistics_links(state),
        "stop_caps": dict(_normalize_stop_caps(state.get("stop_caps"))),
        "stop_caps_enabled": bool(state.get("stop_caps_enabled", True)),
        "delegation_action_zh": str(state.get("delegation_action_zh") or ""),
        "blueprint_known": state["blueprint_known"],
        "blueprint_available": blueprint_available(sess),
        "built": state["built"],
        "abandoned": bool(state.get("abandoned")),
        "energy_deficit_days": int(state.get("energy_deficit_days", 0) or 0),
        "rehab_cost": dict(REHAB_COST),
        "build_cost": BUILD_SITE_COST,
        "entry_resource_floor": dict(WORKSHOP_ENTRY_FLOOR),
        "starter_devices_placed": bool(state.get("starter_devices_placed")),
        "production_speed_mult": PRODUCTION_SPEED_MULT,
        "delegation_on": state["delegation_on"],
        "sandbox_recommended": sandbox,
        "inactive_hint_zh": inactive,
        "comm_trade_available": comm_trade_available(sess),
        "trade_offers": trade_ui,
        "npc_fatigue": fatigue_ui,
        "warehouse": dict(wh),
        "storage_cap": cap,
        "storage_used": _warehouse_total(state),
        "source_ore_buffer": int(state["source_ore_buffer"]),
        "base_resources": sess.resources.as_dict(),
        "grid": grid,
        "devices": devices,
        "build_catalog": build_catalog,
        "npc_roster": [
            {
                "id": k,
                "label_zh": v["label_zh"],
                "device_count": sum(
                    1 for inst in state["cells"].values()
                    if str(inst.get("npc_id") or "").strip() == k
                ),
            }
            for k, v in NPC_PROFILES.items() if k != "temp_worker"
        ],
        "tasks": tasks_ui,
        "active_contract_count": len(state.get("active_contracts") or []),
        "events_log": list(state.get("events_log") or []),
        "total_cycles": int(state.get("total_cycles", 0)),
    }


def _device_summary(spec: dict[str, Any]) -> str:
    ins = spec.get("inputs") or {}
    outs = spec.get("outputs") or {}
    if spec.get("storage_bonus"):
        return f"仓储 +{spec['storage_bonus']}"
    parts = []
    if ins:
        parts.append("消耗 " + "+".join(f"{k}×{v}" for k, v in ins.items()))
    if outs:
        parts.append("产出 " + "+".join(f"{k}×{v}" for k, v in outs.items()))
    if spec.get("energy_per_cycle"):
        parts.append(f"能源 {spec['energy_per_cycle']}/周期")
    return "；".join(parts) if parts else spec["label_zh"]


# 兼容旧 API 名称
build_west_shaft_snapshot = build_workshop_snapshot
