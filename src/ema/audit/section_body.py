"""A catalogue section's own body, written over whatever the base had there."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from docx import Document
from lxml import etree

from ema.audit.base_anchor import MARKER
from ema.audit.base_units import heading_spans_document
from ema.audit.catalogue import CATALOGUE
from ema.core.errors import EmaError
from ema.core.office.blocks import (
    Block,
    ElementLocator,
    Figure,
    Prototypes,
    RenderReport,
)
from ema.core.office.region import replace_region

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_CHAPTERS = {section.id: section.chapter for section in CATALOGUE}
_CAPTION = re.compile(r"^\s*Tabel")


def own_region(document: Any, section_id: str, occurrence: int = 0) -> tuple[int, int]:
    """Body indexes [first, end): after the section's heading, up to the next mapped heading.

    A child's heading ends the region, so a parent's own region is its introduction only.
    """
    spans = heading_spans_document(document)
    starts = [start for item, start, _ in spans if item.section_id == section_id]
    if occurrence >= len(starts):
        raise EmaError("draft_prototype", "Secţiunea lipseşte din bază.", section_id)
    start = starts[occurrence]
    body = list(document.element.body)
    following = [begin for _, begin, _ in spans if begin > start]
    return start + 1, min(following, default=len(body) - 1)


def _text(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def _paragraph(element: etree._Element) -> bool:
    """A paragraph of text a block can be written into: it has a run, and no picture."""
    return (
        element.tag == W + "p"
        and next(element.iter(W + "drawing"), None) is None
        and bool(_text(element).strip())
    )


def _chapter_span(document: Any, section_id: str) -> tuple[int, int]:
    chapter = _CHAPTERS[section_id]
    spans = [
        (start, end)
        for item, start, end in heading_spans_document(document)
        if item.section_id in _CHAPTERS
        and _CHAPTERS[item.section_id] == chapter
        and "." not in item.section_id
    ]
    return spans[0] if spans else (0, 0)


def _prototypes(document: Any, section_id: str, first: int, end: int) -> dict[str, Any]:
    body = list(document.element.body)
    region = body[first:end]
    found: dict[str, Any] = {}
    body_proto = next(
        (item for item in region if _paragraph(item) and not _CAPTION.match(_text(item))), None
    )
    if body_proto is not None:
        found["body"] = body_proto
        found["bullet"] = next(
            (item for item in region if _paragraph(item) and item.find(f".//{W}numPr") is not None),
            body_proto,
        )
    captions = (
        item for item in (*region, *body) if _paragraph(item) and _CAPTION.match(_text(item))
    )
    if (caption := next(captions, None)) is not None:
        found["caption"] = caption
    chapter_start, chapter_end = _chapter_span(document, section_id)
    tables = (item for item in (*region, *body[chapter_start:chapter_end]) if item.tag == W + "tbl")
    if (table := next(tables, None)) is not None:
        found["table"] = table
    return found


def _needed(blocks: list[Block]) -> set[str]:
    names: set[str] = set()
    for block in blocks:
        names.add(block.proto)
        if isinstance(block, Figure):
            names.add(block.caption.proto)
    return names


def replace_section_body(
    source: Path, output: Path, section_id: str, blocks: list[Block], *, keep_base: bool = False
) -> RenderReport:
    """Write ``blocks`` over the section's own region, styled after what the region held."""
    document = Document(str(source))
    count = sum(item.section_id == section_id for item, _, _ in heading_spans_document(document))
    if not count:
        raise EmaError("draft_prototype", "Secţiunea lipseşte din bază.", section_id)
    # Repeated process headings are separate 3.1.x units, all fed by the accepted draft.
    with TemporaryDirectory() as directory:
        current = source
        report: RenderReport | None = None
        for occurrence in reversed(range(count if section_id == "ch3.process" else 1)):
            document = Document(str(current))
            first, end = own_region(document, section_id, occurrence)
            elements = _prototypes(document, section_id, first, end)
            if missing := sorted(_needed(blocks) - set(elements)):
                raise EmaError(
                    "draft_prototype",
                    "Baza nu are un model pentru conţinutul secţiunii.",
                    f"{section_id}: {', '.join(missing)}",
                )
            target = output if occurrence == 0 else Path(directory) / f"{occurrence}.docx"
            body_element: Any = document.element
            region: list[etree._Element] = list(body_element.body)[first:end]
            keep = {
                index
                for index, element in enumerate(region)
                if keep_base
                and (
                    element.tag == W + "tbl"
                    or next(element.iter(W + "drawing"), None) is not None
                    or (
                        element.tag == W + "p"
                        and re.match(r"^\s*(?:Tabel\w*|Fig\w*)\b", _text(element))
                    )
                    or (
                        _text(element).strip() == MARKER
                        and index + 1 < len(region)
                        and re.match(r"^\s*Fig\w*\b", _text(region[index + 1]))
                    )
                )
            }
            report = replace_region(
                current,
                target,
                ElementLocator(first),
                ElementLocator(end + 1),
                blocks,
                Prototypes(elements, _CHAPTERS[section_id], MARKER),
                keep_old=keep,
            )
            current = target
    assert report is not None
    return report
