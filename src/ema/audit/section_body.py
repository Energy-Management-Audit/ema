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
    Missing,
    Prototypes,
    RenderReport,
    Table,
)
from ema.core.office.region import replace_region

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_CHAPTERS = {section.id: section.chapter for section in CATALOGUE}
_CAPTION = re.compile(r"^\s*Tabel")
# The base's equipment, transformer, gas, heating and fleet photos have no dossier images.
# Each number is the figure caption anchor stamped by base_anchor, scoped to its section.
REMOVABLE_PHOTOS = {
    "ch3.equipment": frozenset(
        {
            4,  # First crane photo.
            5,  # Portal crane photo.
            6,  # Port crane photo.
            7,  # Modernized crane photo.
            8,  # Dosing hopper photo.
        }
    ),
    "ch3.electricitate": frozenset({9}),  # Transformer station photo.
    "ch3.gaz": frozenset(
        {
            10,  # Gas regulating station photo.
            11,  # Boiler photo.
            12,  # Heating circuit diagram.
            13,  # Radiator photo.
        }
    ),
    "ch3.carburant": frozenset(
        {
            14,  # First forklift photo.
            15,  # Second forklift photo.
            16,  # Third forklift photo.
            17,  # Fuel tank photo.
        }
    ),
}
_FIGURE_ANCHOR = re.compile(r"^\s*Fig\.?\s*(?:nr\.?\s*)?(\d+)\.")
# The base's lamp and boiler-nameplate tables are not filled by Necesar fields.
REMOVABLE_TABLES = {
    "ch3.electricitate": (4, "tipullămpii"),  # Lamp type and application table.
    "ch3.gaz": (5, "parametrii"),  # One boiler's pressure, temperature and power table.
}
_TABLE_ANCHOR = re.compile(r"^\s*Tabel\w*\s*(?:nr\.?\s*)?(\d+)\.")


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


def _removable(region: list[etree._Element], section_id: str, blocks: list[Block]) -> set[int]:
    removed: set[int] = set()
    has_figure = any(isinstance(block, Figure) for block in blocks)
    has_table = any(isinstance(block, Table) for block in blocks)
    for index, element in enumerate(region):
        caption = _FIGURE_ANCHOR.match(_text(element)) if element.tag == W + "p" else None
        if (
            caption
            and int(caption.group(1)) in REMOVABLE_PHOTOS.get(section_id, ())
            and not has_figure
        ):
            removed.add(index)
            if index and (
                next(region[index - 1].iter(W + "drawing"), None) is not None
                or _text(region[index - 1]).strip() == MARKER
            ):
                removed.add(index - 1)
        if element.tag != W + "tbl" or has_table:
            continue
        first = element.find(W + "tr")
        if first is None:
            continue
        header = "".join(_text(cell) for cell in first.findall(W + "tc"))
        slot = REMOVABLE_TABLES.get(section_id)
        previous = region[index - 1] if index else None
        anchor = _TABLE_ANCHOR.match(_text(previous)) if previous is not None else None
        if (
            slot is not None
            and anchor is not None
            and int(anchor.group(1)) == slot[0]
            and re.sub(r"\W+", "", header.casefold()).startswith(slot[1])
        ):
            removed.add(index)
            if index and _CAPTION.match(_text(region[index - 1])):
                removed.add(index - 1)
    return removed


def replace_section_body(
    source: Path, output: Path, section_id: str, blocks: list[Block], *, keep_base: bool = False
) -> RenderReport:
    """Write ``blocks`` over the section's own region, styled after what the region held."""
    document = Document(str(source))
    count = sum(item.section_id == section_id for item, _, _ in heading_spans_document(document))
    if not count:
        raise EmaError("draft_prototype", "Secţiunea lipseşte din bază.", section_id)
    # Repeated process headings are separate 3.1.x units. Until the draft maps its passages to
    # stages, it fills the first unit and the others keep the marker rather than repeat it.
    with TemporaryDirectory() as directory:
        current = source
        report: RenderReport | None = None
        for occurrence in reversed(range(count if section_id == "ch3.process" else 1)):
            document = Document(str(current))
            first, end = own_region(document, section_id, occurrence)
            elements = _prototypes(document, section_id, first, end)
            unit: list[Block] = blocks if occurrence == 0 else [Missing("body", MARKER)]
            if missing := sorted(_needed(unit) - set(elements)):
                raise EmaError(
                    "draft_prototype",
                    "Baza nu are un model pentru conţinutul secţiunii.",
                    f"{section_id}: {', '.join(missing)}",
                )
            target = output if occurrence == 0 else Path(directory) / f"{occurrence}.docx"
            body_element: Any = document.element
            region: list[etree._Element] = list(body_element.body)[first:end]
            removable: set[int] = _removable(region, section_id, unit) if keep_base else set()
            keep = {
                index
                for index, element in enumerate(region)
                if keep_base
                and index not in removable
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
                unit,
                Prototypes(elements, _CHAPTERS[section_id], MARKER),
                keep_old=keep,
            )
            current = target
    assert report is not None
    return report
