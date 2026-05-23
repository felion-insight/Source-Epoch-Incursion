"""CLI smoke tests: python -m narrative_ai [npc|source|mgmt|beat]"""

from __future__ import annotations

import argparse
import sys

from narrative_ai.memory import InteractionTurn, NpcMemoryStore, SimulationSnapshot
from narrative_ai.npc_agent import NpcAgent
from narrative_ai.source_agent import SourceAgent, SourceSession


def cmd_npc() -> None:
    store = NpcMemoryStore(
        npc_id="karen",
        conspiracy_tier_unlocked=1,
        long_term_notes=["本章：玩家刚查阅过损坏的设备日志。"],
    )
    store.record_turn(InteractionTurn("player", "玩家坚持要把最后一份医疗包留给伤员而非军械库。"))
    store.emotional.trust = 62.0

    agent = NpcAgent("karen", store)
    sim = SimulationSnapshot(resources={"medical": 4, "energy": 22}, last_decision_tag="supply_medical_first", last_decision_label_zh="优先医疗")
    text = agent.generate(
        mode="scene_line",
        player_context="指挥室简短汇报后，玩家看向你，等待你对资源分配的反应。",
        sim=sim,
        max_tokens=400,
    )
    print(text)


def cmd_source() -> None:
    sess = SourceSession(attunement=35, conspiracy_tier_unlocked=2)
    sess.add_exchange("你真的存在吗？", "潮线……许多名字，同一道盐痕。听闻，不必命名。")
    agent = SourceAgent()
    q = "如果我放大聆听，会失去自己吗？"
    r = agent.whisper(question=q, session=sess, extra_world="地下监听站刚完成校准，低频嗡鸣渗入骨骼。")
    print(r)


def cmd_mgmt() -> None:
    from narrative_ai.management import resolve_decision

    spec = resolve_decision("mine_deepen")
    if spec is None:
        print("unknown tag", file=sys.stderr)
        raise SystemExit(1)
    store = NpcMemoryStore("dr_lin", conspiracy_tier_unlocked=1)
    store.emotional.trust = 40.0
    agent = NpcAgent("dr_lin", store)
    ctx = f"经营结果：{spec.label_zh}。叙事提示：{spec.player_facing_hint}"
    print(agent.generate(mode="management_comment", player_context=ctx, max_tokens=200))


def cmd_beat() -> None:
    from narrative_ai.generator import NarrativeGenerator
    from narrative_ai.schemas import BeatRequest, WorldContext

    gen = NarrativeGenerator()
    beat = BeatRequest(
        intent="写一段卡伦在走廊截住玩家的短对话，暗示有人在看报告，但不要点名灰镜。",
        world=WorldContext(
            title="源纪元 · 岸线侵入",
            premise="边境基地，岸线威胁升级。",
            tone="克制、悬疑",
            player_role="代理指挥官",
            current_location="基地走廊",
            constraints="阴谋层仅到 Tier1。",
        ),
        prior_summary="玩家刚修复通讯阵列。",
        format_hint="纯对白+少量动作括号。",
    )
    print(gen.generate_beat(beat, max_tokens=500))


def main() -> None:
    p = argparse.ArgumentParser(description="Narrative AI tooling (smoke / integration).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("npc", help="NPC line with memory + sim snapshot")
    sub.add_parser("source", help="Source whisper with session history")
    sub.add_parser("mgmt", help="Management decision reaction (林博士 / 加大开采例)")
    sub.add_parser("beat", help="Legacy beat generator (no per-NPC store)")

    args = p.parse_args()
    if args.cmd == "npc":
        cmd_npc()
    elif args.cmd == "source":
        cmd_source()
    elif args.cmd == "mgmt":
        cmd_mgmt()
    elif args.cmd == "beat":
        cmd_beat()


if __name__ == "__main__":
    main()
