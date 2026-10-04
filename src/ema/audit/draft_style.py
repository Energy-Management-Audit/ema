"""A redacted, runtime-only section example from the configured audit base, and its length.

A section's example is its own text, without its subsections' (D8): the chapter call sees every
subsection's own example beside it.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from docx import Document

from ema.audit.headings import headings, map_headings
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.workspace import Workspace

_NUMBER = re.compile(r"\d+(?:[.,/–-]\d+)*\s*%?")
_WORD = re.compile(r"\b[A-ZĂÂÎȘȚŞŢ][A-Za-z0-9ĂÂÎȘȚăâîșțŞŢşţ]*\b")
_CAPTION = re.compile(r"^\s*(?:Tabel|Fig)")


@dataclass(frozen=True)
class Example:
    text: str
    words: int


def _fold(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn"
    ).casefold()


def _mask_identity(value: str, identity: tuple[str, ...]) -> str:
    folded = ""
    positions: list[int] = []
    for index, char in enumerate(value):
        for normalized in _fold(char):
            folded += " " if normalized.isspace() else normalized
            positions.append(index)
    spans: list[tuple[int, int]] = []
    for term in identity:
        parts = _fold(term).split()
        if parts:
            pattern = r"\s+".join(re.escape(part) for part in parts)
            spans.extend(
                (positions[m.start()], positions[m.end() - 1] + 1)
                for m in re.finditer(pattern, folded)
            )
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        value = value[:start] + "{{…}}" + value[end:]
    return value


def _mask_names(value: str) -> str:
    # Sentence-initial names resemble ordinary words, so mask both to avoid a leak.
    return _WORD.sub("{{…}}", value)


def _own_texts(base: Path, sections: Collection[str]) -> dict[str, list[str]]:
    """Each section's own paragraphs in the base, from its first heading to the next heading."""
    paragraphs = Document(str(base)).paragraphs
    starts = sorted(item.index for item in headings(base))
    found: dict[str, list[str]] = {}
    for item in map_headings(base, "audit-01").mapped:
        if item.section_id not in sections or item.section_id in found:
            continue
        begin = item.heading.index
        end = next((index for index in starts if index > begin), len(paragraphs))
        found[item.section_id] = [
            paragraph.text
            for paragraph in paragraphs[begin + 1 : end]
            if paragraph.text.strip() and not _CAPTION.match(paragraph.text)
        ]
    return found


def style_examples(
    base: Path, identity: tuple[str, ...], sections: Collection[str]
) -> dict[str, Example]:
    """Per section, its redacted own text and that text's word count before redaction."""
    terms = tuple(sorted(identity, key=len, reverse=True))
    return {
        section: Example(
            _mask_names(_NUMBER.sub("{{…}}", _mask_identity("\n".join(own), terms))),
            sum(len(text.split()) for text in own),
        )
        for section, own in _own_texts(base, sections).items()
    }


def style_example(base: Path, identity: tuple[str, ...], section: str) -> str:
    example = style_examples(base, identity, (section,)).get(section)
    return example.text if example is not None else ""


def configured_examples(ws: Workspace, sections: Collection[str]) -> dict[str, Example]:
    settings = load_settings(ws)
    base, identity_file = settings.audit_base_document, settings.audit_base_identity
    if base is None or identity_file is None or not base.is_file() or not identity_file.is_file():
        logging.getLogger(__name__).warning(
            "Audit style example unavailable: audit_base_document or audit_base_identity"
        )
        return {}
    try:
        identity = cast(object, json.loads(identity_file.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise EmaError(
            "audit_base_missing", "Baza auditului nu este configurată.", "audit_base_identity"
        ) from exc
    if not isinstance(identity, list) or not all(
        isinstance(item, str) for item in cast(list[object], identity)
    ):
        raise EmaError(
            "audit_base_missing", "Baza auditului nu este configurată.", "audit_base_identity"
        )
    return style_examples(base, tuple(cast(list[str], identity)), sections)
