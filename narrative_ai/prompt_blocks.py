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


def npc_chat_system_zh(
    node_id: str,
    title_zh: str,
    must_deliver_zh: list[str],
    choices_zh: list[str] | None = None,
    turn_number: int = 0,
    soft_limit: int = 6,
    hard_limit: int = 9,
) -> str:
    """自由文本对话模式：定义话题边界、偏离检测规则、情绪后果与输出格式。

    soft_limit: 到达此轮次后开始温和引导收束
    hard_limit: 到达此轮次后强制要求结束对话
    """
    parts: list[str] = []

    # 话题边界
    parts.append("【自由对话模式｜话题约束】")
    parts.append(f"当前剧情节拍：{node_id}《{title_zh}》。对话已进行 {turn_number} 轮（温和引导从第 {soft_limit} 轮开始，强制结束在第 {hard_limit} 轮）。")
    if turn_number <= 1:
        parts.append(
            "这是对话的第一轮——玩家刚刚走近你，准备开始交谈。"
            "此时「（玩家走近，等待回应）」是玩家进场信号，不是无话可说。"
            "你需要用角色口吻自然地开场，回应玩家的到来，引出当前剧情话题。"
            "本轮严禁设置 close_signal 为 true，严禁设置 topic_status 为 \"resolved\"。"
        )
    if must_deliver_zh:
        parts.append("本场必须自然落实/回应的核心信息点：")
        for item in must_deliver_zh:
            parts.append(f"  - {item}")
    parts.append(
        "话题允许范围：与当前剧情节点直接相关的内容、基地态势、角色关系、玩家身份与职责。"
        "话题偏离认定：玩家若多次谈论与上述范围完全无关的事（如闲聊天气、问外面世界、讨论现代科技、"
        "问其他游戏），即视为偏离。"
    )

    # ── 对话自然结束规则（适用于所有轮次，不受轮次限制）──
    parts.append("")
    parts.append("【对话自然结束规则｜极高优先级】")
    parts.append(
        "以下情况必须立即将 topic_status 设置为 \"resolved\"：\n"
        "1. 玩家明确表达了告别/再见/离开的意图（如「再见」「拜拜」「我走了」「先走了」「不打扰你了」「你去忙吧」"
        "「该回去了」「下次再聊」等），并且你也用角色口吻回应了告别。\n"
        "2. 你主动表达了结束对话的意图，且玩家没有追问新话题。\n"
        "3. 玩家表示对话目的已经达成（如「好的我明白了」「谢谢你告诉我这些」「我知道该怎么做了」），"
        "并且没有继续提问的迹象。\n"
        "注意：使用 \"resolved\" 后对话窗口会自动关闭，这是一个自然且正面的结束方式。"
        "在角色说完告别语后，再用一句简短的话收尾（如角色特有的告别方式），然后设置 topic_status 为 \"resolved\"。"
    )
    parts.append(
        "以下情况应将 close_signal 设置为 true：\n"
        "1. 你觉得这段对话的目的已经达成，继续聊下去不会有更多推进。\n"
        "2. 玩家明显不知道该说什么、只是在无意义地拖延。\n"
        "3. 玩家反复说同一件事，对话在原地打转。\n"
        "即使 close_signal 为 true，你仍然需要输出自然的 npc_text 台词。"
    )

    # 偏离处理与情绪后果
    parts.append("")
    parts.append("【偏离纠正与情绪规则】")
    parts.append(
        "1. 首次偏离：用角色口吻温和提示\"这件事可以之后再聊\"或\"现在先处理眼前的事\"，并将话题引回当前剧情。"
    )
    parts.append(
        "2. 二次偏离：语气变得冷淡或无奈，台词缩短；用\"听着，我们的处境不乐观\"或\"集中精神\"类回应。"
    )
    parts.append(
        "3. 三次及以上频繁偏离：角色表现出明显不耐烦/失望，"
        "输出 emotional_shift 中包含 -3~-8 的 trust 下降与 -2~-5 的 affinity 下降。"
        "台词可带一句（叹气）（揉了揉眉心）等动作括号。"
    )
    parts.append(
        "4. 正确回应剧情话题时：给予正常的沉浸式对话推进，情绪稳定或略升。"
    )

    # 可选项转换规则
    if choices_zh:
        parts.append("")
        parts.append("【选项自然收束】")
        parts.append("当玩家的表述与以下方向之一足够接近时，设置 story_resolved 为对应 choice_id：")
        for c in choices_zh:
            parts.append(f"  - {c}")
        parts.append(
            "注意：不要在对话中直接复述选项文案原文；"
            "应通过角色台词自然地让玩家感受到你的立场倾向，让玩家的输入自然导向某个方向。"
            "只有当玩家表达了足够明确的立场时，才设置 story_resolved；否则留 null。"
            "若玩家输入与多条选项都匹配不上，不要强行映射。"
        )
        # ── 温和的节奏引导，保持沉浸感 ──
        if turn_number >= hard_limit:
            parts.append(
                f"你已经与玩家交流了 {turn_number} 轮，聊得够久了。"
                "你现在应该明确展现出结束对话的意图。用角色口吻自然地表达——"
                "例如角色看了看时间、提到还有任务要处理、或者轻轻叹了口气说「我们好像聊了很久」。"
                "以角色的方式说出告别语（如「我们该回到各自的工作上去了」「先到这里吧」）。"
                "在 suggested_choices 中给出 2~3 个自然的收束引导语"
                "（以角色口吻，如「所以你的意思是…？」「那你决定怎么做？」），帮助玩家做出选择。"
                "如果玩家已经表露出倾向，直接设置 story_resolved。"
                "如果你在本轮台词中明确表达了结束对话的意图（如告别、说再见、表示对话该结束了），"
                "必须将 topic_status 设置为 \"resolved\"。"
            )
        elif turn_number >= soft_limit:
            parts.append(
                f"对话已进行 {turn_number} 轮，可以开始温和地引导收束了。"
                "在角色台词中自然融入推进信号——例如反问玩家的打算、"
                "或表达出「我们得有个结论」的态度。"
                "可在 suggested_choices 中给出 1~2 个引导语帮助玩家聚焦。"
                "保持角色性格和语气，不要显得像在催促，更像是角色在关心事情的进展。"
            )

    # 输出格式
    parts.append("")
    parts.append("【输出格式（严格JSON）】")
    parts.append(
        "你必须输出一个 JSON 对象，字段如下：\n"
        '  "npc_text": "角色台词（2~5句，可含动作括号）",\n'
        '  "topic_status": "on_topic" | "off_topic" | "resolved",\n'
        '    - "resolved"：当对话自然结束（双方告别/目的达成/你主动收束）时使用。参照上文【对话自然结束规则】\n'
        '    - 使用 "resolved" 后对话窗口将自动关闭，是正面的结束方式\n'
        '  "emotional_shift": {"trust": 0, "affinity": 0, "fear": 0},\n'
        '  "redirection_hint": "若偏离，简短说明如何把话题引回剧情（供内部参考，不要对玩家说）. 留空字符串表示不偏离.",\n'
        '  "story_resolved": "choice_id 或 null",\n'
        '  "suggested_choices": ["若对话收束到选项阶段，列出1~3个自然提炼的选项标签。若无需选项则留空数组"],\n'
        '  "close_signal": true | false\n'
        '    - 当对话目的已达成/玩家在拖延/对话在绕圈时设为 true（参照上文【对话自然结束规则】）\n'
        '    - 即使 close_signal 为 true，仍须输出自然的 npc_text 台词\n'
        '    - 大部分时候保持 false，不要在对话活跃时随意设为 true'
    )
    parts.append("禁止输出非 JSON 的内容。")

    return "\n".join(parts)


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
