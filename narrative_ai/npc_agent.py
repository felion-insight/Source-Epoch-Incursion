from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from narrative_ai.config import Settings
from narrative_ai.memory import NpcMemoryStore, SimulationSnapshot
from narrative_ai.openai_client import ChatClient
from narrative_ai.prompt_blocks import (
    memory_block,
    npc_chat_system_zh,
    npc_sheet_block,
    spoiler_guard_block,
    story_beat_system_zh,
    world_header_block,
)
from narrative_ai.schemas import ChatCompletionRequest, ChatMessage
from narrative_ai.validators import mentions_recent_memory_heuristic


Mode = Literal["scene_line", "branch_options", "custom_reply", "management_comment", "chat_free"]


@dataclass
class ChatTurnResult:
    """自由对话单轮结果。"""
    npc_text: str = ""
    topic_status: str = "on_topic"   # on_topic | off_topic | resolved
    emotional_shift: dict[str, float] | None = None
    redirection_hint: str = ""
    story_resolved: str | None = None  # choice_id 或 null
    suggested_choices: list[str] | None = None
    close_signal: bool = False  # AI 判断对话应该结束了（不显示在界面中）
    raw_json: dict[str, Any] | None = None


@dataclass
class NpcAgent:
    """
    One agent instance per NPC session (or cheaply recreate with same store).
    """

    npc_id: str
    store: NpcMemoryStore
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self._client = ChatClient(self.settings or Settings())

    def _base_messages(
        self, sim: SimulationSnapshot | None, story_beat_system: str | None = None
    ) -> list[ChatMessage]:
        system_parts = [
            "你是《源纪元·岸线侵入》中的可扮演 NPC。保持人设与信念，不破坏已锁定阴谋层。",
            world_header_block(max_tier_inject=self.store.conspiracy_tier_unlocked),
            npc_sheet_block(self.npc_id),
            memory_block(self.store, sim),
            spoiler_guard_block(self.store),
        ]
        if story_beat_system:
            system_parts.append(story_beat_system.strip())
        return [ChatMessage(role="system", content="\n\n".join(system_parts))]

    def generate(
        self,
        *,
        mode: Mode,
        player_context: str,
        sim: SimulationSnapshot | None = None,
        temperature: float = 0.72,
        max_tokens: int | None = 900,
        extra_user: str | None = None,
        story_beat_system: str | None = None,
    ) -> str:
        instructions = self._mode_instructions(mode)
        user = "\n\n".join(
            [
                "## 情境与任务",
                player_context.strip(),
                "## 生成模式",
                instructions,
            ]
        )
        if extra_user:
            user = user + "\n\n## 额外要求\n" + extra_user.strip()

        req = ChatCompletionRequest(
            messages=[
                *self._base_messages(sim, story_beat_system=story_beat_system),
                ChatMessage(role="user", content=user),
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._client.complete(req)

    def generate_with_memory_retry(
        self,
        *,
        mode: Mode,
        player_context: str,
        sim: SimulationSnapshot | None = None,
        temperature: float = 0.72,
        max_tokens: int | None = 900,
        extra_user: str | None = None,
        story_beat_system: str | None = None,
        max_rounds: int = 2,
    ) -> tuple[str, str]:
        """
        若近期有交互记录却未通过「记忆回溯」启发式，则追加一条用户指令再请求一次。
        返回 (文本, 说明) 说明为 ok / retry_applied / still_weak。
        """
        text = self.generate(
            mode=mode,
            player_context=player_context,
            sim=sim,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_user=extra_user,
            story_beat_system=story_beat_system,
        )
        ok, _ = mentions_recent_memory_heuristic(self.store, text)
        if ok or max_rounds < 2:
            return text, "ok" if ok else "still_weak"

        bump = (
            "\n【系统附加要求】近期交互摘要非空，但上一稿未体现。请在本轮对白中**明确引用**其中一条"
            "（可转述为半句话，勿机械复述编号）。"
        )
        text2 = self.generate(
            mode=mode,
            player_context=player_context,
            sim=sim,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_user=(extra_user or "") + bump,
            story_beat_system=story_beat_system,
        )
        ok2, _ = mentions_recent_memory_heuristic(self.store, text2)
        return text2, "retry_applied" if ok2 else "still_weak"

    def chat_turn(
        self,
        *,
        player_text: str,
        conversation_history: list[dict[str, str]] | None = None,
        choice_labels: list[dict[str, str]] | None = None,
        node_id: str = "",
        node_title_zh: str = "",
        must_deliver_zh: list[str] | None = None,
        sim: SimulationSnapshot | None = None,
        turn_number: int = 0,
        soft_limit: int = 6,
        hard_limit: int = 9,
        temperature: float = 0.72,
        max_tokens: int | None = 600,
    ) -> ChatTurnResult:
        """自由文本多轮对话：AI 评估话题偏离、情绪变化，并输出结构化 JSON。

        参数：
        - player_text: 玩家当前输入
        - conversation_history: [{"role":"npc"|"player","text":"..."}]
        - choice_labels: 当前节点可选项的标签列表（含 choice_id）
        - 其余参数：节点上下文
        """
        # 构建 choice 提示（供 AI 判断何时收束到选项）
        choices_hint: list[str] | None = None
        if choice_labels:
            choices_hint = [f"{c['id']}: {c['label_zh']}" for c in choice_labels]

        chat_system = npc_chat_system_zh(
            node_id=node_id,
            title_zh=node_title_zh,
            must_deliver_zh=must_deliver_zh or [],
            choices_zh=choices_hint,
            turn_number=turn_number,
            soft_limit=soft_limit,
            hard_limit=hard_limit,
        )

        # 基础系统消息
        base_msgs = self._base_messages(sim)
        # 替代 story_beat_system 为 chat 专用系统提示
        beat_override = story_beat_system_zh(node_id, node_title_zh, must_deliver_zh or [])
        base_msgs.append(ChatMessage(role="system", content=chat_system))
        base_msgs.append(ChatMessage(role="system", content=beat_override))

        # 对话历史
        messages: list[ChatMessage] = list(base_msgs)
        if conversation_history:
            for turn in conversation_history[-10:]:  # 保留最近10轮
                role = "assistant" if turn.get("role") == "npc" else "user"
                content = turn.get("text", "")
                if content.strip():
                    messages.append(ChatMessage(role=role, content=content.strip()))

        # 当前玩家输入
        messages.append(ChatMessage(role="user", content=player_text.strip()))

        req = ChatCompletionRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw_response = self._client.complete(req)

        # 解析 JSON
        result = _parse_chat_json(raw_response, player_text)
        return result

    @staticmethod
    def _mode_instructions(mode: Mode) -> str:
        if mode == "scene_line":
            return (
                "输出本回合 NPC 对白（可适当加一句动作/神态，以括号标注）。"
                "长度控制在中等；必须自然呼应「近期交互摘要」中至少一条（若无则勿强行）。"
            )
        if mode == "branch_options":
            return (
                "玩家将看到若干选项。请输出 2-4 个选项，每行以 A/B/C… 开头，后面是选项摘要；"
                "不要剧透隐藏身份；可为每个选项隐含不同态度后果（不必明说）。"
            )
        if mode == "custom_reply":
            return (
                "玩家刚输入了一句自由文本问题。仅用该 NPC 身份回答，**最多两句**。"
                "不能透露未解锁阴谋；无法用已知信息回答时使用回避语。"
            )
        if mode == "management_comment":
            return (
                "玩家刚完成一项基地经营决策。请用简短台词（一至三句）表达你对该决策的态度或担忧，"
                "可带一句动作括号；呼应记忆与信任档。"
            )
        if mode == "chat_free":
            return (
                "玩家正在与你进行自由对话。根据聊天系统提示中的【输出格式】指令，"
                "以 JSON 格式返回包含台词、话题状态、情绪变化的结构化响应。"
            )
        raise ValueError(mode)


def _parse_chat_json(raw_response: str, fallback_text: str) -> ChatTurnResult:
    """解析 LLM 返回的 JSON，失败则降级为纯文本。"""
    text = (raw_response or "").strip()

    # 尝试提取 JSON（处理 ```json 包裹等情况）
    json_str = text
    # 匹配 ```json ... ``` 或 ``` ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        json_str = m.group(1).strip()
    # 也尝试找纯 { ... }
    elif "{" in text:
        # 找到第一个 { 到最后一个 }
        start = text.index("{")
        end = text.rindex("}")
        json_str = text[start : end + 1]

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        # 降级：当作纯文本台词
        return ChatTurnResult(
            npc_text=text,
            topic_status="on_topic",
        )

    npc_text = str(parsed.get("npc_text") or text)
    topic_status = str(parsed.get("topic_status") or "on_topic")
    emotional_shift = parsed.get("emotional_shift")
    if isinstance(emotional_shift, dict):
        emotional_shift = {
            "trust": float(emotional_shift.get("trust", 0)),
            "affinity": float(emotional_shift.get("affinity", 0)),
            "fear": float(emotional_shift.get("fear", 0)),
        }
    else:
        emotional_shift = None

    redirection_hint = str(parsed.get("redirection_hint") or "")
    story_resolved = parsed.get("story_resolved")
    if story_resolved:
        story_resolved = str(story_resolved)
    else:
        story_resolved = None

    suggested_choices = parsed.get("suggested_choices")
    if isinstance(suggested_choices, list):
        suggested_choices = [str(s) for s in suggested_choices]
    else:
        suggested_choices = None

    close_signal = bool(parsed.get("close_signal", False))

    return ChatTurnResult(
        npc_text=npc_text,
        topic_status=topic_status,
        emotional_shift=emotional_shift,
        redirection_hint=redirection_hint,
        story_resolved=story_resolved,
        suggested_choices=suggested_choices,
        close_signal=close_signal,
        raw_json=parsed,
    )
