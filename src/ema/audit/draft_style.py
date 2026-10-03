"""A redacted, runtime-only section example from the configured audit base."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import cast

from docx import Document

from ema.audit.headings import map_headings
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.workspace import Workspace

_NUMBER = re.compile(r"\d+(?:[.,/–-]\d+)*\s*%?")
_WORD = re.compile(r"\b[A-ZĂÂÎȘȚŞŢ][A-Za-z0-9ĂÂÎȘȚăâîșțŞŢşţ]*\b")


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


def style_example(base: Path, identity: tuple[str, ...], section: str) -> str:
    paragraphs = Document(str(base)).paragraphs
    mapped = map_headings(base, "audit-01").mapped
    heading = next((item.heading for item in mapped if item.section_id == section), None)
    if heading is None:
        return ""
    end = min(
        (
            item.heading.index
            for item in mapped
            if item.heading.index > heading.index and item.heading.level <= heading.level
        ),
        default=len(paragraphs),
    )
    example = "\n".join(p.text for p in paragraphs[heading.index + 1 : end] if p.text.strip())
    example = _mask_identity(example, tuple(sorted(identity, key=len, reverse=True)))
    return _mask_names(_NUMBER.sub("{{…}}", example))


def configured_style_example(ws: Workspace, section: str) -> str:
    settings = load_settings(ws)
    base, identity_file = settings.audit_base_document, settings.audit_base_identity
    if base is None or identity_file is None or not base.is_file() or not identity_file.is_file():
        logging.getLogger(__name__).warning(
            "Audit style example unavailable: audit_base_document or audit_base_identity"
        )
        return ""
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
    return style_example(base, tuple(cast(list[str], identity)), section)
