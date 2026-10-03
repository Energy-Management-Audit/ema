"""Dossier text as bounded pages and searchable passages for the Fill agent."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import PurePath

PAGE_CHARS = 6000
PASSAGE_CHARS = 300
SEARCH_LIMIT = 8
# Models often drop Romanian diacritics or mix the comma and cedilla forms.
_LETTER = {letter: f"[{group}]" for group in ("aăâ", "iî", "sşș", "tţț") for letter in group}


def file_ids(names: Iterable[str]) -> dict[str, str]:
    """The short ids the task lists the files under: F1, F2, ... in dossier order."""
    return {f"F{number}": name for number, name in enumerate(names, 1)}


def resolve_name(wanted: str, names: Sequence[str]) -> str | None:
    """A file named by its id, its exact name, or its name without the extension."""
    ids = file_ids(names)
    if wanted in ids:
        return ids[wanted]
    if wanted in names:
        return wanted
    stems = [name for name in names if PurePath(name).stem == wanted]
    return stems[0] if len(stems) == 1 else None


def windows(text: str) -> list[str]:
    """Cut text into windows of at most PAGE_CHARS, at a line or word break when one is near."""
    parts: list[str] = []
    while len(text) > PAGE_CHARS:
        cut = text.rfind("\n", PAGE_CHARS // 2, PAGE_CHARS)
        if cut < 0:
            cut = text.rfind(" ", PAGE_CHARS // 2, PAGE_CHARS)
        cut = cut + 1 if cut >= 0 else PAGE_CHARS
        parts.append(text[:cut])
        text = text[cut:]
    parts.append(text)
    return parts


def _pattern(words: str) -> re.Pattern[str]:
    letters = "".join(_LETTER.get(char, re.escape(char)) for char in words.casefold())
    return re.compile(letters, re.IGNORECASE)


def _passages(
    pages: Mapping[str, Sequence[str]], pattern: re.Pattern[str]
) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for file_id, texts in pages.items():
        for page, text in enumerate(texts, 1):
            end = -1
            for match in pattern.finditer(text):
                if match.start() < end:
                    continue
                start, end = max(0, match.start() - PASSAGE_CHARS), match.end() + PASSAGE_CHARS
                found.append({"file": file_id, "page": page, "text": text[start:end]})
                if len(found) == SEARCH_LIMIT:
                    return found
    return found


def search(pages: Mapping[str, Sequence[str]], query: str) -> list[dict[str, object]]:
    """Passages around the whole query; failing that, around any of its words."""
    found = _passages(pages, _pattern(query))
    if found:
        return found
    words = [word for word in re.findall(r"\w+", query) if len(word) >= 3]
    if not words:
        return []
    return _passages(pages, re.compile("|".join(_pattern(word).pattern for word in words), re.I))
