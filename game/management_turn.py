"""经营决策 → 资源与隐藏变量；标签与 narrative_ai.management 注册表一致。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from narrative_ai.management import resolve_decision

from .hidden_state import BaseResources, PlayerHiddenVars

RES_KEYS = frozenset({"energy", "food", "medical", "intel"})

HV_LABEL_ZH: dict[str, str] = {
    "SYNC": "同调压力",
    "HUMAN": "人性倾向",
    "COUNCIL": "议会关系",
    "PURIFY": "净空会倾向",
    "ECHO": "回声集团倾向",
    "INCURSION": "岸线侵入",
    "RESET": "纪元重置计数",
    "INSIGHT": "洞察",
}

RES_LABEL_ZH: dict[str, str] = {
    "energy": "能源储备",
    "food": "食物补给",
    "medical": "医疗资源",
    "intel": "情报资产",
}


@dataclass
class _Delta:
    res: dict[str, int]
    hv: dict[str, float | int]


def _label_for_other_tag(conflict_tag: str) -> str:
    spec = resolve_decision(conflict_tag)
    if spec:
        short = spec.label_zh
        for prefix in (
            "源矿机：",
            "医疗/实验室：",
            "通讯阵列：",
            "防御工事：",
            "地下监听站：",
            "资源分配：",
            "拒绝回声",
            "接受回声",
            "同意净空",
        ):
            if short.startswith(prefix):
                short = short.replace(prefix, "", 1)
        return short
    return conflict_tag


def _d(**kwargs: float | int) -> _Delta:
    res = {k: int(v) for k, v in kwargs.items() if k in RES_KEYS}
    hv = {k: v for k, v in kwargs.items() if k not in RES_KEYS}
    return _Delta(res=res, hv=hv)


def _apply(d: _Delta, res: BaseResources, hv: PlayerHiddenVars) -> None:
    if d.res:
        res.apply(**d.res)
    for k, v in d.hv.items():
        hv.apply_delta(k, v)


_MUTEX_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"mine_deepen", "mine_limit"}),
    frozenset({"accept_echo_aid", "reject_echo_aid"}),
)


_MANAGEMENT_DELTAS: dict[str, _Delta] = {
    "comm_array_encrypt": _d(energy=-20, intel=10, COUNCIL=-15),
    "comm_array_broadcast": _d(energy=-30, intel=5),
    "mine_deepen": _d(energy=40, INCURSION=20, SYNC=10, COUNCIL=10),
    "mine_limit": _d(energy=-20, INCURSION=-10, SYNC=-5, COUNCIL=-5),
    "lab_neural_scan": _d(medical=-15, intel=15),
    "lab_sync_suppressor": _d(medical=-25, SYNC=-25),
    "defense_fortify": _d(energy=-40, INCURSION=-30),
    "listen_station_on": _d(energy=-50, intel=30, SYNC=20),
    "supply_medical_first": _d(medical=-10, HUMAN=10),
    "reject_echo_aid": _d(energy=-30, intel=10, SYNC=-5, ECHO=-5),
    "accept_echo_aid": _d(energy=40, intel=-10, ECHO=25, COUNCIL=-15),
    "purge_partial_mine": _d(energy=-50, INCURSION=-20, PURIFY=20, HUMAN=-15),
}


def get_management_delta(tag: str) -> _Delta | None:
    return _MANAGEMENT_DELTAS.get(tag)


def _resource_shortfall(res: BaseResources, d: _Delta) -> list[str]:
    """若资源不足以支付负数增量，列出缺口说明。"""
    bad: list[str] = []
    for k, delta in d.res.items():
        if delta >= 0:
            continue
        cur = int(getattr(res, k))
        need = -delta
        if cur < need:
            label = RES_LABEL_ZH.get(k, k)
            bad.append(f"{label} 需要 ≥{need}（当前 {cur}）")
    return bad


def management_validation_error_zh(
    tag: str,
    res: BaseResources,
    _hv: PlayerHiddenVars,
    applied_tags: Iterable[str],
    pending_tags: Iterable[str] | None = None,
) -> str | None:
    """None 表示可执行；否则为面向玩家的拒绝原因。"""
    if tag not in _MANAGEMENT_DELTAS:
        return "未知的经营决议标签"

    applied_set = frozenset(applied_tags) | frozenset(pending_tags or ())
    if tag in applied_set:
        return "该决议在本存档中已经执行过，无法重复立项"

    d = _MANAGEMENT_DELTAS[tag]
    for grp in _MUTEX_GROUPS:
        if tag not in grp:
            continue
        hit = grp & applied_set
        for other in hit:
            if other == tag:
                continue
            return f"与早前决议「{_label_for_other_tag(other)}」互斥，无法同时生效"

    short = _resource_shortfall(res, d)
    if short:
        return "资源不足以执行：" + "；".join(short)
    return None


def simulate_preview_numbers(
    tag: str,
    res: BaseResources,
    hv: PlayerHiddenVars,
) -> tuple[dict[str, dict[str, int | float]], dict[str, dict[str, int | float]]]:
    """返回 resources / hidden 两块预测，便于 UI 展示。"""
    d = get_management_delta(tag)
    resources: dict[str, dict[str, int | float]] = {}
    hvs: dict[str, dict[str, int | float]] = {}
    if not d:
        return resources, hvs

    for k, delta in d.res.items():
        before = int(getattr(res, k))
        resources[k] = {
            "label": RES_LABEL_ZH.get(k, k),
            "before": float(before),
            "delta": float(delta),
            "after": float(max(0, before + int(delta))),
        }

    for k, delta in d.hv.items():
        before_raw = getattr(hv, k)
        if k == "RESET":
            before = float(int(before_raw))
            di = float(int(delta))
            after_f = max(0.0, before + di)
            hvs[k] = {
                "label": HV_LABEL_ZH.get(k, k),
                "before": before,
                "delta": di,
                "after": after_f,
            }
            continue
        before_f = float(before_raw)
        dv = float(delta)
        after = max(0.0, min(100.0, before_f + dv))
        hvs[k] = {
            "label": HV_LABEL_ZH.get(k, k),
            "before": round(before_f, 1),
            "delta": round(dv, 1),
            "after": round(after, 1),
        }
    return resources, hvs


def serialize_management_preview_payload(
    tag: str,
    res: BaseResources,
    hv: PlayerHiddenVars,
    applied_tags: Iterable[str],
    pending_tags: Iterable[str] | None = None,
) -> dict[str, object]:
    """供 facility_hints JSON 嵌入。"""
    err = management_validation_error_zh(tag, res, hv, applied_tags, pending_tags=pending_tags)
    hint_line = ""
    spec = resolve_decision(tag)
    if spec:
        hint_line = spec.player_facing_hint
    resources_map, hvmap = simulate_preview_numbers(tag, res, hv)
    reactors_list: list[dict[str, str]] = []
    if spec:
        reactors_list = [{"npc_id": a, "tone_zh": b} for a, b in spec.reactors]

    res_list: list[dict[str, object]] = []
    for k, v in resources_map.items():
        res_list.append(
            {
                "key": k,
                "label_zh": v["label"],
                "before": v["before"],
                "delta": v["delta"],
                "after": v["after"],
            }
        )

    hv_list: list[dict[str, object]] = []
    for k, v in hvmap.items():
        hv_list.append(
            {
                "key": k,
                "label_zh": v["label"],
                "before": v["before"],
                "delta": v["delta"],
                "after": v["after"],
            }
        )

    return {
        "tag": tag,
        "blocked": bool(err),
        "blocked_reason_zh": err or "",
        "narrative_hint_zh": hint_line,
        "reactors": reactors_list,
        "resources": res_list,
        "hidden_vars": hv_list,
    }


def apply_management_tag(tag: str, res: BaseResources, hv: PlayerHiddenVars) -> bool:
    d = _MANAGEMENT_DELTAS.get(tag)
    if d is None:
        return False
    _apply(d, res, hv)
    return True
