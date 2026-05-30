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
    return story_beat_system_zh(n.id, n.title_zh, sess.get_active_must_deliver_zh())


def record_player_line(sess: GameSession, npc_id: str, summary: str) -> None:
    from narrative_ai.memory import InteractionTurn

    st = sess.get_memory_store(npc_id)
    st.record_turn(InteractionTurn("player", summary))
    sess.save_memory_store(st)


# ── 自由文本对话桥接 ────────────────────────────────────────────

# 选项自然浮现的轮次阈值：对话进行到此轮次后，前端会将剧情选项显示在对话界面中
# 玩家可以随时点击选项来推进剧情，同时保留自由输入能力
CHOICE_UNVEIL_TURNS = 5


def get_conversation_turn_limits(sess: "GameSession") -> tuple[int, int]:
    """根据当前剧情进度（act）返回 (温和引导轮次, 强制结束轮次)。

    剧情越往后，对话轮数上限越低——玩家已熟悉世界观，NPC 也有更紧迫的任务。
    """
    try:
        node = sess.current_node()
        act = getattr(node, "act", "act1")
    except Exception:
        act = "act1"

    limits = {
        "prologue": (4, 7),   # 序章：新手引导期，稍宽松但不至于让玩家无话可说
        "act1":     (3, 6),   # 第一幕：适中
        "act2":     (3, 5),   # 第二幕：局势趋紧
        "act3":     (2, 4),   # 第三幕：冲突升级，简短交流
        "finale":   (2, 3),   # 终局：局势紧张，直奔主题
    }
    return limits.get(act, (6, 9))


def start_conversation(sess: GameSession, npc_id: str) -> None:
    """标记自由对话开始，绑定当前剧情节点。"""
    sess.active_conversation_npc = npc_id
    sess.active_conversation_node = sess.current_node_id
    sess.conversation_turn_count = 0
    sess.conversation_off_topic_count = 0
    sess.conversation_history = []


def end_conversation(sess: GameSession, closed_by_npc: bool = False) -> None:
    """清理自由对话状态。closed_by_npc 表示 NPC 主动结束了对话（不允许再发起）。"""
    if closed_by_npc and sess.active_conversation_npc:
        # 记录：该 NPC 在当前节点主动结束了对话，短期内不允许再次发起
        if not hasattr(sess, "conversation_closed_by_npc"):
            sess.conversation_closed_by_npc = {}
        sess.conversation_closed_by_npc[sess.active_conversation_npc] = sess.active_conversation_node
    sess.active_conversation_npc = None
    sess.active_conversation_node = None
    sess.conversation_turn_count = 0
    sess.conversation_off_topic_count = 0
    sess.conversation_history = []


def can_start_conversation_with(sess: GameSession, npc_id: str) -> tuple[bool, str | None]:
    """检查是否允许与该 NPC 开始自由对话。返回 (可以对话, 拒绝原因)。"""
    node_id = sess.current_node_id
    closed = getattr(sess, "conversation_closed_by_npc", {})
    if closed.get(npc_id) == node_id:
        return False, "该去工作了"
    return True, None


def apply_chat_emotional_shift(sess: GameSession, npc_id: str, emotional_shift: dict[str, float]) -> dict[str, float]:
    """将 AI 返回的情绪变化应用到 NPC 记忆存储，返回应用后的值。"""
    store = sess.get_memory_store(npc_id)
    trust_d = float(emotional_shift.get("trust", 0))
    aff_d = float(emotional_shift.get("affinity", 0))
    fear_d = float(emotional_shift.get("fear", 0))

    store.emotional.trust = max(0.0, min(100.0, store.emotional.trust + trust_d))
    store.emotional.affinity = max(0.0, min(100.0, store.emotional.affinity + aff_d))
    store.emotional.fear = max(0.0, min(100.0, store.emotional.fear + fear_d))
    sess.save_memory_store(store)

    return {
        "trust": store.emotional.trust,
        "affinity": store.emotional.affinity,
        "fear": store.emotional.fear,
    }


def narrative_chat_choice_labels(sess: GameSession) -> list[dict[str, str]] | None:
    """获取当前节点的可选项标签（供 AI 提示注入）。"""
    node = sess.current_node()
    active = sess.get_active_choices()
    if not active:
        return None
    return [{"id": c.id, "label_zh": c.label_zh} for c in active]


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
