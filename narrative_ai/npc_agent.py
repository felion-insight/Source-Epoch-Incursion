from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from narrative_ai.config import Settings
from narrative_ai.memory import NpcMemoryStore, SimulationSnapshot
from narrative_ai.openai_client import ChatClient
from narrative_ai.prompt_blocks import memory_block, npc_sheet_block, spoiler_guard_block, world_header_block
from narrative_ai.schemas import ChatCompletionRequest, ChatMessage
from narrative_ai.validators import mentions_recent_memory_heuristic


Mode = Literal["scene_line", "branch_options", "custom_reply", "management_comment"]


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
        raise ValueError(mode)
