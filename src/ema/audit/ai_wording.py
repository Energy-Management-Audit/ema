"""The one rule for AI wording: a deliverable never mentions AI (draft sections and the final)."""

from __future__ import annotations

import re

# "AI"/"IA" only as capital words: "ai" and "ia" are ordinary Romanian ("angajaţi ai unor").
_ACRONYM = re.compile(r"\b(?:AI|IA)\b")
_PHRASE = re.compile(
    r"\b(?:inteligen[țţt][aă] artificial[ăa]|model(?:ul)? de limbaj|chatgpt|gpt|claude|gemini|"
    r"openai|llm|generat automat|asistent virtual)\b",
    re.I,
)


def ai_wording(text: str) -> str | None:
    """The first AI wording in the text, else None."""
    found = [match for pattern in (_ACRONYM, _PHRASE) if (match := pattern.search(text))]
    return min(found, key=lambda match: match.start()).group(0) if found else None
