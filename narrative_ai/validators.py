from __future__ import annotations

from narrative_ai.memory import NpcMemoryStore


def mentions_recent_memory_heuristic(store: NpcMemoryStore, generated_text: str) -> tuple[bool, str]:
    """
    Cheap guard per design doc: at least echo one recent exchange when history exists.

    Matches if any substring of a summary (length>=4) appears in output.
    False negative/positive possible — game may still LLM-verify later.
    """
    text = generated_text.lower()
    for turn in store.short_term:
        s = turn.summary.strip()
        if len(s) < 4:
            continue
        key = s[: min(48, len(s))].lower()
        if key and key in text:
            return True, "matched"
    if len(store.short_term) == 0:
        return True, "no_history_skipped"
    # Try looser token match: first content word longer than 3 chars from each summary
    for turn in store.short_term:
        for w in turn.summary.replace("，", " ").replace("。", " ").split():
            ww = w.strip("，。？！,.")
            if len(ww) >= 4 and ww.lower() in text:
                return True, "token_matched"
    return False, "no_recent_callback"
