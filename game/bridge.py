"""与 narrative_ai 的衔接：SimulationSnapshot、经营标签、可选 AI 生成。"""

from __future__ import annotations

from dataclasses import replace

from narrative_ai.management import resolve_decision
from narrative_ai.memory import NpcMemoryStore, SimulationSnapshot
from narrative_ai.npc_agent import NpcAgent
from narrative_ai.prompt_blocks import story_beat_system_zh
from narrative_ai.source_agent import SourceAgent, SourceSession

from .management_turn import apply_management_tag, management_validation_error_zh
from .narrative_map import narrative_gate_management_decision_zh
from .narrative_progress import apply_management_narrative_hooks
from .session import GameSession
from .sim_sandbox import append_bulletin_zh, sandbox_policy


def build_simulation_snapshot(sess: GameSession) -> SimulationSnapshot:
    hv = sess.hidden
    return SimulationSnapshot(
        resources=sess.resources.as_dict(),
        last_decision_tag=sess.last_management_tag,
        last_decision_label_zh=sess.last_decision_label_zh,
        shoreline_intrusion_percent=float(hv.INCURSION),
        hidden_vars=hv.as_snapshot_dict(),
    )


def _commit_management_tag_effect(sess: GameSession, tag: str) -> None:
    """已通过校验后对真实会话落地决算（不写队列）。"""
    if not apply_management_tag(tag, sess.resources, sess.hidden):
        raise RuntimeError("内部错误：决算标签无法在资源模拟层落地")
    sess.applied_management_tags.append(tag)
    spec = resolve_decision(tag)
    sess.last_management_tag = tag
    sess.last_decision_label_zh = spec.label_zh if spec else tag
    if tag == "listen_station_on":
        sess.plot.enable("listen_station_built")
    elif tag == "mine_deepen":
        sess.plot.enable("mine_deep_lit")
    elif tag == "accept_echo_aid":
        sess.plot.enable("echo_aid_accepted")
    apply_management_narrative_hooks(sess, tag)


def management_queue_precheck_zh(sess: GameSession) -> str | None:
    """确保待决队列可按当前资源/互斥顺序完整落地。"""
    pend = list(sess.management_queue_pending)
    if not pend:
        return None
    r2 = replace(sess.resources)
    h2 = replace(sess.hidden)
    sim_done = list(sess.applied_management_tags)
    tail = pend[:]
    while tail:
        t = tail[0]
        err = management_validation_error_zh(t, r2, h2, sim_done, pending_tags=tail[1:])
        if err:
            return err
        if not apply_management_tag(t, r2, h2):
            return "待办决算包含不可模拟的标签。"
        sim_done.append(t)
        tail.pop(0)
    return None


def flush_management_queue(sess: GameSession) -> tuple[list[str], str | None]:
    blocked = management_queue_precheck_zh(sess)
    if blocked:
        return [], blocked
    drained: list[str] = []
    while sess.management_queue_pending:
        tag = sess.management_queue_pending.pop(0)
        _commit_management_tag_effect(sess, tag)
        drained.append(tag)
    return drained, None


def apply_management_decision(sess: GameSession, tag: str) -> tuple[bool, str | None, bool]:
    """决算：第三项为是否在静默期写入待办队列（queued）。"""
    gate = narrative_gate_management_decision_zh(sess, tag)
    if gate:
        return False, gate, False

    pend_list = sess.management_queue_pending
    applied = sess.applied_management_tags
    if tag in pend_list:
        return False, "该决议已在待办队列中，无需重复登记。", False
    err = management_validation_error_zh(tag, sess.resources, sess.hidden, applied, pending_tags=pend_list)
    if err:
        return False, err, False

    if str(sess.story_phase).strip() == "Sandbox":
        pol = sandbox_policy(tag)
        if pol == "queue":
            pend_list.append(tag)
            spec = resolve_decision(tag)
            lab = spec.label_zh if spec else tag
            append_bulletin_zh(sess, f"待办决算：「{lab}」。退出静默后将正式立项并计入资源账本。")
            return True, None, True

        _commit_management_tag_effect(sess, tag)
        return True, None, False

    _commit_management_tag_effect(sess, tag)
    return True, None, False


def npc_agent_for(sess: GameSession, npc_id: str) -> NpcAgent:
    store = sess.get_memory_store(npc_id)
    store.conspiracy_tier_unlocked = max(store.conspiracy_tier_unlocked, sess.conspiracy_tier_unlocked)
    return NpcAgent(npc_id, store)


def narrative_story_beat_system(sess: GameSession) -> str:
    """与当前 story 节点对齐的系统提示块，注入 NPC 生成。"""
    n = sess.current_node()
    return story_beat_system_zh(n.id, n.title_zh, n.must_deliver_zh)


def record_player_line(sess: GameSession, npc_id: str, summary: str) -> None:
    from narrative_ai.memory import InteractionTurn

    st = sess.get_memory_store(npc_id)
    st.record_turn(InteractionTurn("player", summary))
    sess.save_memory_store(st)


def source_session_from(sess: GameSession) -> SourceSession:
    s = SourceSession(
        attunement=float(sess.hidden.SYNC),
        conspiracy_tier_unlocked=sess.conspiracy_tier_unlocked,
        understanding_hidden=float(sess.hidden.INSIGHT),
    )
    s.lines.extend(sess.source_lines)
    return s


def persist_source_exchange(sess: GameSession, player_q: str, source_a: str) -> None:
    sess.source_lines.append(f"玩家：{player_q.strip()}\n源：{source_a.strip()}")


def default_source_agent() -> SourceAgent:
    return SourceAgent()
