"""Identity terms of the audit base's own client, which must never reach a client's audit."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from ema.audit.headings import map_headings

_IDENTIFIERS = (
    r"\b(?:RO)?\d{7,10}\b",  # CUI
    r"\bJ\d{1,2}/\d{1,6}/\d{4}\b",  # registration
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    r"(?:https?://|www\.)[^\s]+",
    r"\b0\d{9}\b",
)


def _general_text(base: Path) -> str:
    paragraphs = Document(str(base)).paragraphs
    mapping = map_headings(base, "audit-01")
    heading = next(
        item.heading for item in mapping.mapped if item.section_id == "ch2.date_generale"
    )
    later = [
        item.heading.index
        for item in mapping.mapped
        if item.heading.index > heading.index and item.heading.level <= heading.level
    ]
    end = min(later, default=len(paragraphs))
    return " ".join(paragraph.text for paragraph in paragraphs[heading.index : end])


def derive_identity(base: Path) -> tuple[str, ...]:
    """The base client's full name first, then its name words and ch. 2.1 identifiers."""
    company = base.stem.split("AUDIT ENERGETIC ", 1)[1].rsplit(" - ", 1)[0]
    words = re.findall(r"[^\W\d_]{5,}", company)
    general = _general_text(base)
    identifiers = [
        match for pattern in _IDENTIFIERS for match in re.findall(pattern, general, flags=re.I)
    ]
    return tuple(dict.fromkeys((company, *words, *identifiers)))
