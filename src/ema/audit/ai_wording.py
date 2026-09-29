"""The one rule for AI wording in deliverable text."""

from __future__ import annotations

import re

_PHRASE = re.compile(
    r"\b(?:inteligen[tţț]\w*\s+artificial\w*|generat\w*\s+automat\w*|generar\w*\s+automat\w*|"
    r"model\w*\s+(?:de\s+limbaj|lingvistic\w*)|asistent\w*\s+virtual\w*|"
    r"chatgpt|gpt-?\d\w*|copilot|openai|llm)\b",
    re.I,
)
# Lowercase ai/ia are ordinary Romanian words, even in a sentence about automation.
_AMBIGUOUS = re.compile(r"\b(?:AI|IA|(?i:Claude|Gemini))\b")
_CONTEXT = re.compile(r"\b(?:algoritm|generar|generat|asistent|automat|inteligen[tţț])\w*\b", re.I)
_SENTENCE = re.compile(r"[^.!?\n]+")


def ai_wording(text: str) -> str | None:
    """The first forbidden wording, with ambiguous names scoped to their sentence."""
    found = list(_PHRASE.finditer(text))
    for sentence in _SENTENCE.finditer(text):
        if _PHRASE.search(sentence.group()) or _CONTEXT.search(sentence.group()):
            found.extend(_AMBIGUOUS.finditer(text, sentence.start(), sentence.end()))
    return min(found, key=lambda match: match.start()).group() if found else None
