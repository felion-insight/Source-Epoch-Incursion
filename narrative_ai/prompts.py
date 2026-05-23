from __future__ import annotations

from narrative_ai.schemas import BeatRequest, ChatMessage, WorldContext


def system_narrative_designer() -> str:
    return (
        "You are a narrative designer for an interactive story game. "
        "Respect tone, pacing, and player agency. "
        "Follow the user's output format instructions exactly."
    )


def user_beat_prompt(br: BeatRequest) -> str:
    w = br.world
    sections = [
        "## World",
        _world_block(w),
        "## Story so far (summary)",
        br.prior_summary or "(none — this is early.)",
        "## Task",
        br.intent,
    ]
    if br.format_hint:
        sections.extend(["## Output format", br.format_hint])
    return "\n\n".join(sections)


def _world_block(w: WorldContext) -> str:
    lines = [
        f"- Title: {w.title or '—'}",
        f"- Premise: {w.premise or '—'}",
        f"- Tone: {w.tone or '—'}",
        f"- Player role: {w.player_role or '—'}",
        f"- Location: {w.current_location or '—'}",
    ]
    if w.known_npcs:
        lines.append(f"- NPCs: {w.known_npcs}")
    if w.recent_events:
        lines.append(f"- Recent events: {w.recent_events}")
    if w.constraints:
        lines.append(f"- Constraints: {w.constraints}")
    return "\n".join(lines)


def messages_for_beat(br: BeatRequest) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=system_narrative_designer()),
        ChatMessage(role="user", content=user_beat_prompt(br)),
    ]
