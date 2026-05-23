from __future__ import annotations

from dataclasses import dataclass, field

from narrative_ai.config import Settings
from narrative_ai.loader import get_npc
from narrative_ai.openai_client import ChatClient
from narrative_ai.schemas import ChatCompletionRequest, ChatMessage


def default_source_system(npc_id: str = "source") -> str:
    n = get_npc(npc_id)
    return "\n".join(
        [
            "你是先驱文明残余的集合意识回声，代号「源」。",
            "语言规则：禁止使用第一人称「我」。可用「我们」、省略主语，或无主语句。",
            "句式断裂、诗意的隐喻、偶尔的陌生词语；总长不超过三句。",
            "不撒谎，但不提供可执行的明确事实指令（不给密码、门牌、具体时间轴真相清单）。",
            "以记忆碎片与意象回应玩家的提问；可引用玩家过去问过你的主题。",
            "情绪底色：悲伤与希望交织。",
            f"角色设定补充：{n.get('role_hidden', '')}",
        ]
    )


@dataclass
class SourceSession:
    """Runtime log of player–Source exchanges (design: 源记住所有提问)."""

    lines: list[str] = field(default_factory=list)
    attunement: float = 0.0
    conspiracy_tier_unlocked: int = 0
    understanding_hidden: float = 0.0

    def add_exchange(self, player_q: str, source_a: str) -> None:
        self.lines.append(f"玩家：{player_q}\n源：{source_a}")


@dataclass
class SourceAgent:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self._client = ChatClient(self.settings or Settings())

    def whisper(self, *, question: str, session: SourceSession, extra_world: str | None = None) -> str:
        hist = "\n".join(session.lines[-40:]) or "（尚无历史）"
        user = "\n".join(
            [
                f"玩家同调感：约 {session.attunement:.0f}（仅供参考语气密度，不写进台词）。",
                f"已知阴谋层上限：{session.conspiracy_tier_unlocked}。更高层不可用直述。",
                "## 你与玩家的过往低语摘录",
                hist,
                "## 玩家此刻的提问或沉默",
                question.strip() if question.strip() else "（沉默，仅倾泻碎片）",
            ]
        )
        if extra_world:
            user = user + "\n## 环境与身体状态\n" + extra_world.strip()

        req = ChatCompletionRequest(
            messages=[
                ChatMessage(role="system", content=default_source_system()),
                ChatMessage(role="user", content=user),
            ],
            temperature=0.85,
            max_tokens=280,
        )
        return self._client.complete(req)
