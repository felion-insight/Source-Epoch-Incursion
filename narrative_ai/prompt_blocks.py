from __future__ import annotations

import json
from typing import Any

from narrative_ai.loader import get_npc, load_world
from narrative_ai.memory import NpcMemoryStore, SimulationSnapshot, trust_instructions


def world_header_block(max_tier_inject: int | None = None) -> str:
    w = load_world()
    lines = [
        f"作品：{w.get('title', '')}",
        f"年代：{w.get('year_label', '')}",
        f"世界观基调：{w.get('global_tone', '')}",
        f"玩家设定：{w.get('premise_player', '')}",
        f"表层冲突：{w.get('surface_conflict', '')}",
    ]
    tiers: list[dict[str, Any]] = w.get("conspiracy_tiers") or []
    if max_tier_inject is not None and tiers:
        lines.append("当前剧情允许提及的阴谋层次（不得超过此深度的具体设定）：")
        for t in tiers:
            tier_n = int(t.get("tier", 0))
            if tier_n <= max_tier_inject:
                lines.append(f"  Tier{tier_n}：{t.get('player_facing', '')}")
    return "\n".join(lines)


def npc_sheet_block(npc_id: str) -> str:
    n = get_npc(npc_id)
    beliefs = "\n".join(f"  - {b}" for b in (n.get("core_beliefs") or []))
    constraints = "\n".join(f"  - {c}" for c in (n.get("ai_constraints") or []))
    social = ", ".join(n.get("social_links") or []) or "（无）"
    memories = "\n".join(f"  - {m}" for m in (n.get("core_memories") or []))
    return "\n".join(
        [
            f"角色：{n.get('display_name')} / {n.get('display_name_en')}",
            f"表面身份：{n.get('role_surface', '')}",
            f"隐藏身份（对你保密，勿主动剧透给玩家）：{n.get('role_hidden', '')}",
            f"核心记忆：\n{memories}",
            f"特质：{', '.join(n.get('traits') or [])}",
            f"语言风格：{n.get('speech_style', '')}",
            f"台词约束：\n{constraints}",
            f"转折条件摘要：{n.get('turn_condition', '')}",
            f"社交关联：{social}",
            f"不可违背的核心信念：\n{beliefs}",
            f"记忆规则：{n.get('memory_rule_ref', '')}",
        ]
    )


def memory_block(store: NpcMemoryStore, sim: SimulationSnapshot | None) -> str:
    parts: list[str] = []
    if store.long_term_notes:
        parts.append("设计者补充的长期记忆：\n" + "\n".join(f"  - {x}" for x in store.long_term_notes))
    st = store.short_term_lines()
    if st:
        parts.append("与玩家的近期交互摘要（须在台词中自然地呼应至少一处，除非角色刻意装傻）：\n" + "\n".join(st))
    else:
        parts.append("与玩家的近期交互摘要：（尚无）")
    if store.social_rumors:
        parts.append("社交传闻（其他角色对玩家的说法）：\n" + "\n".join(f"  - {r}" for r in store.social_rumors))
    if store.plot_flags:
        parts.append("已发生的剧情标记：\n" + "\n".join(sorted(store.plot_flags)))
    emo = store.emotional
    parts.append(
        "情感数值（仅作语气参考）：\n"
        f"  信任={emo.trust:.0f} 好感={emo.affinity:.0f} 恐惧={emo.fear:.0f}\n"
        f"  {trust_instructions(emo.trust)}"
    )
    if sim is not None:
        if sim.resources:
            parts.append("基地资源快照：\n" + json.dumps(sim.resources, ensure_ascii=False))
        if sim.last_decision_tag:
            parts.append(f"最近一次经营决策：{sim.last_decision_label_zh or sim.last_decision_tag}")
        if sim.shoreline_intrusion_percent is not None:
            parts.append(f"岸线侵入进度感：约 {sim.shoreline_intrusion_percent:.0f}%")
        if sim.hidden_vars:
            parts.append("玩家隐藏变量快照（对白语气参考，勿向玩家逐项念名单）：\n" + json.dumps(sim.hidden_vars, ensure_ascii=False))
    return "\n\n".join(parts)


def spoiler_guard_block(store: NpcMemoryStore) -> str:
    return (
        f"已解锁阴谋层数上限：{store.conspiracy_tier_unlocked}。"
        "不得主动说出高于该层的核心设定；必要时用含糊、省略或岔开话题。"
        "自定义提问若在能力外，用「我不想谈这个」「现在不是时候」类回应，不编造关键线索。"
    )


def story_beat_system_zh(node_id: str, title_zh: str, must_deliver_zh: list[str]) -> str:
    """供 NPC 系统提示：锁定本场须落实的剧情事实（与 story_nodes.must_deliver_zh 对齐）。"""
    if not must_deliver_zh:
        return f"【本场剧情节拍】节点 {node_id}《{title_zh}》。无额外必达事实条目。"
    bullets = "\n".join(f"- {t}" for t in must_deliver_zh)
    return (
        f"【本场剧情节拍｜系统约束】节点 {node_id}《{title_zh}》。\n"
        "下列信息须在本轮台词中自然落实或呼应（勿逐条照念，勿扩写未解锁阴谋层）：\n"
        f"{bullets}"
    )


def source_whisper_scene_zh(node_id: str, title_zh: str, must_deliver_zh: list[str]) -> str:
    """供「源」用户消息附加上下文：隐喻呼应 must_deliver，禁止直述超出阴谋层的事实。"""
    base = f"剧情节点 {node_id}《{title_zh}》。"
    if not must_deliver_zh:
        return base + "以意象与断裂句式回应，不必点名具体设施。"
    bullets = "\n".join(f"- {t}" for t in must_deliver_zh)
    return (
        f"{base}\n"
        "本场低语须在隐喻/意象中与下列主题共振（勿澄清为可操作情报，勿超过已解锁阴谋层）：\n"
        f"{bullets}"
    )
