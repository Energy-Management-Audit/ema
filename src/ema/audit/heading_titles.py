"""Keep body heading case separate from the catalogue's TOC and UI labels."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from docx.oxml.ns import qn

from ema.audit.catalogue import CATALOGUE
from ema.core.office.blocks import Block, Paragraph, Prototypes

MARKER = "[de completat]"


def body_title(text: str, level: int, prototype: str) -> str:
    text = text.translate(str.maketrans("şţŞŢ", "șțȘȚ"))
    prototype = prototype.replace(MARKER, "")
    if level <= 2 or prototype.isupper():
        return text.upper().replace(MARKER.upper(), MARKER)
    if prototype.islower():
        return text.lower().replace(MARKER.lower(), MARKER)
    return text


def heading_blocks(blocks: list[Block], prototypes: Prototypes) -> list[Block]:
    """New headings use the case of their own named prototype at level three."""
    sections = {section.id: section for section in CATALOGUE}
    result: list[Block] = []
    for block in blocks:
        formatted = block
        if isinstance(block, Paragraph) and block.proto.startswith("heading:"):
            section = sections[block.proto.removeprefix("heading:")]
            prototype = "".join(
                node.text or "" for node in prototypes.elements[block.proto].iter(qn("w:t"))
            )
            level = 2 if section.parent == "ch4" else 3
            formatted = replace(
                block,
                segments=[
                    body_title(segment, level, prototype) if isinstance(segment, str) else segment
                    for segment in block.segments
                ],
            )
        result.append(formatted)
    return result


def normalize_body_heading(paragraph: Any, level: int) -> None:
    for node in paragraph.iter(qn("w:t")):
        text = node.text or ""
        text = text.replace("măsurator", "măsurător").replace("MĂSURATOR", "MĂSURĂTOR")
        node.text = body_title(text, level, "") if level <= 2 else text


def own_toc_title(text: str, template: str | None, catalogue_title: str) -> str:
    """Sentence-case the template's wording, retaining each heading's slot values."""
    acronyms = set(re.findall(r"\b[^\W\d_]{2,}\b", catalogue_title))
    acronyms = {word for word in acronyms if word.isupper()}

    def sentence(value: str) -> str:
        value = value.lower()
        for acronym in acronyms:
            value = re.sub(r"\b" + re.escape(acronym) + r"\b", acronym, value, flags=re.I)
        return value

    pieces = re.split(r"(\{[a-z_]+\})", template or catalogue_title)
    pattern = "".join("(.+?)" if piece.startswith("{") else re.escape(piece) for piece in pieces)
    match = re.fullmatch(pattern, text, re.IGNORECASE)
    if match and any(not piece.startswith("{") and piece.strip() for piece in pieces):
        values = iter(match.groups())
        title = "".join(
            next(values) if piece.startswith("{") else sentence(piece) for piece in pieces
        )
    elif text.isupper():
        title = sentence(text)
    else:
        title = text
    return title[:1].upper() + title[1:]


def heading_snapshot(document: Any, spans: list[Any]) -> list[tuple[str, Any, str]]:
    return [
        (
            item.section_id,
            document.element.body[start],
            "".join(node.text or "" for node in document.element.body[start].iter(qn("w:t"))),
        )
        for item, start, _ in spans
    ]


def title_changes(snapshot: list[tuple[str, Any, str]]) -> list[str]:
    changes: list[str] = []
    for section_id, paragraph, before in snapshot:
        after = "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
        if before != after:
            changes.append(f"G2/G3 {section_id} heading text: {before} → {after}")
    for section in CATALOGUE:
        if section.chapter == 5 and section.id.endswith(("_fisa", "_rezultate")):
            before = section.title.replace("măsurător", "măsurator")
            changes.append(f"G1 {section.id} catalogue title: {before} → {section.title}")
    return changes
