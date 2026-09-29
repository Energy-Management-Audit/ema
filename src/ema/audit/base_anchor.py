"""Stamp a local audit base with explicit fixed and variable paragraph anchors."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ema.audit.base_numeric import approved_fixed_text, has_number
from ema.audit.base_parts import (
    YEAR,
    Binding,
    image_refs,
    images_approved,
    part_classification,
)
from ema.audit.base_units import heading_spans_document
from ema.audit.catalogue import CATALOGUE
from ema.audit.chapter_four import MONTHS
from ema.audit.heading_titles import MARKER, body_title
from ema.audit.headings import MappedHeading, slot_values
from ema.core.office.anchors import stamp

_TITLES = {section.id: section.title for section in CATALOGUE}
_CAPTION = re.compile(r"^\s*(Fig\.|Figura|Tabelul|Tabel|Graficul|Grafic)\s*(?:nr\.?\s*)?\d+", re.I)
_EXTENT = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"
_NUMBERED = re.compile(r"^\s*\d+(?:\.\d+)*[.\s-]+")
_MONTH = re.compile(rf"^(?:{'|'.join(month.casefold() for month in MONTHS)})\s+\d{{4}}$")


@dataclass(frozen=True)
class Anchor:
    slot: str
    section: str
    part: str
    classification: str
    binding: Binding | None = None
    # The picture box (EMU width, height) a cover photo is fitted into.
    box: tuple[int, int] | None = None


def _paragraph_text(paragraph: Any) -> str:
    return "".join(node.text or "" for node in paragraph.iter(qn("w:t")))


def _replace_text(paragraph: Any, old: str, new: str) -> None:
    if not old:
        return
    nodes = list(paragraph.iter(qn("w:t")))
    text = "".join(node.text or "" for node in nodes)
    for match in reversed(list(re.finditer(re.escape(old), text, flags=re.IGNORECASE))):
        offset = 0
        first = last = -1
        first_at = last_at = 0
        for index, node in enumerate(nodes):
            end = offset + len(node.text or "")
            if first < 0 and match.start() < end:
                first, first_at = index, match.start() - offset
            if first >= 0 and match.end() <= end:
                last, last_at = index, match.end() - offset
                break
            offset = end
        if first < 0 or last < 0:
            continue
        prefix = (nodes[first].text or "")[:first_at]
        suffix = (nodes[last].text or "")[last_at:]
        nodes[first].text = prefix + new + (suffix if first == last else "")
        if first != last:
            for node in nodes[first + 1 : last]:
                node.text = ""
            nodes[last].text = suffix


def _set_text(paragraph: Any, value: str) -> None:
    children = list(paragraph)
    first_run = next((child for child in children if child.tag == qn("w:r")), None)
    run_properties = first_run.find(qn("w:rPr")) if first_run is not None else None
    for child in children:
        if child.tag != qn("w:pPr"):
            paragraph.remove(child)
    run = OxmlElement("w:r")
    if run_properties is not None:
        run.append(deepcopy(run_properties))
    node = OxmlElement("w:t")
    node.text = value
    run.append(node)
    paragraph.append(run)


def _paragraphs(element: Any) -> list[Any]:
    return [
        paragraph
        for paragraph in element.iter(qn("w:p"))
        if not any(parent.tag == qn("w:p") for parent in paragraph.iterancestors())
    ]


def _fixed(section: str) -> bool:
    return section.startswith("ch1") or section in {
        "ch6.indicatori",
        "ch6.generale",
        "ch7",
    }


def _heading_slot(name: str, values: dict[str, str], client_name: str) -> str:
    if name == "client":
        return client_name
    value = values.get(name, "")
    return value if name == "period" and value and approved_fixed_text(value) else MARKER


def _collapsed(text: str) -> str:
    return " ".join(text.split()).casefold()


def _binding(section: str, text: str, identity: tuple[str, ...], seat: bool) -> Binding | None:
    """The source a variable paragraph is filled from, judged on the base's own text.

    A picture-only cover paragraph no digest keeps is her client's own photo: the job's.
    """
    if section == "front" and not text:
        return "cover_photo"
    if seat:
        return "address"
    if text == _collapsed(identity[0]):
        return "client_name"
    if section == "front" and _MONTH.fullmatch(text):
        return "report_month"
    return None


def _approved(paragraph: Any, part: Any) -> bool:
    """Reviewed fixed text; a paragraph holding only pictures is reviewed by their bytes."""
    text = _paragraph_text(paragraph)
    if text.strip():
        return approved_fixed_text(text)
    return bool(image_refs(paragraph)) and images_approved(paragraph, part)


def _classification(
    section: str, paragraph: Any, identity: tuple[str, ...], *, heading: bool, part: Any = None
) -> str:
    result = _text_classification(section, paragraph, identity, heading=heading, part=part)
    if result == "fixed" and not images_approved(paragraph, part):
        return "variable"
    return result


def _text_classification(
    section: str, paragraph: Any, identity: tuple[str, ...], *, heading: bool, part: Any
) -> str:
    properties = paragraph.find(qn("w:pPr"))
    style = properties.find(qn("w:pStyle")) if properties is not None else None
    if style is not None and (style.get(qn("w:val")) or "").startswith("TOC"):
        return "structural"
    if heading:
        return "structural"
    text = _paragraph_text(paragraph).casefold()
    # A blank line is fixed; one holding a drawing (a picture, a chart, a shape) is judged.
    if (
        not text.strip()
        and not image_refs(paragraph)
        and next(paragraph.iter(qn("w:drawing")), None) is None
    ):
        return "fixed"
    if (
        section == "front"
        and (style is not None or _approved(paragraph, part))
        and not any(term.casefold() in text for term in identity)
        and (not has_number(text) or approved_fixed_text(_paragraph_text(paragraph)))
    ):
        return "fixed"
    if (
        _fixed(section)
        and not any(term.casefold() in text for term in identity)
        and (not has_number(text) or approved_fixed_text(_paragraph_text(paragraph)))
    ):
        return "fixed"
    return "variable"


def _section_by_body_index(document: Any) -> tuple[dict[int, str], dict[int, MappedHeading]]:
    spans = heading_spans_document(document)
    sections: dict[int, str] = {}
    headings: dict[int, MappedHeading] = {}
    body = list(document.element.body)
    for item, start, end in spans:
        headings[start] = item
        for index in range(start, min(end, len(body))):
            sections[index] = item.section_id
    return sections, headings


def numeric_variable_texts(document: Any, identity: tuple[str, ...]) -> tuple[str, ...]:
    """Capture numeric base paragraphs that must disappear from the final package."""
    sections, headings = _section_by_body_index(document)
    values: list[str] = []
    for index, element in enumerate(document.element.body):
        section = sections.get(index, "front")
        for ordinal, paragraph in enumerate(_paragraphs(element)):
            if index in headings and ordinal == 0:
                continue
            text = _paragraph_text(paragraph).strip()
            if (
                has_number(text)
                and _classification(section, paragraph, identity, heading=False, part=document.part)
                == "variable"
            ):
                values.append(text)
    return tuple(dict.fromkeys(values))


def anchor_document(  # noqa: C901, PLR0912, PLR0915
    document: Any, client_name: str, identity: tuple[str, ...]
) -> tuple[Anchor, ...]:
    if not identity or any(not word.strip() for word in identity):
        raise ValueError("base identity denylist is required")
    sections, headings = _section_by_body_index(document)
    body = list(document.element.body)
    anchors: list[Anchor] = []
    seats: set[Any] = set()
    caption_numbers = {"figure": 0, "table": 0, "chart": 0}
    bookmark_id = (
        max(
            (
                int(node.get(qn("w:id"), "0"))
                for node in document.element.iter(qn("w:bookmarkStart"))
            ),
            default=0,
        )
        + 1
    )
    for index, element in enumerate(body):
        section = sections.get(index, "front")
        for ordinal, paragraph in enumerate(_paragraphs(element)):
            heading = index in headings and ordinal == 0
            classification = _classification(
                section, paragraph, identity, heading=heading, part=document.part
            )
            if (
                classification == "fixed"
                and has_number(_paragraph_text(paragraph))
                and not approved_fixed_text(_paragraph_text(paragraph))
            ):
                raise ValueError(f"unlisted fixed number at body_{index}_{ordinal}")
            slot = f"body_{index}_{ordinal}"
            caption = _CAPTION.match(_paragraph_text(paragraph)) if not heading else None
            caption_kind = None
            if caption is not None:
                label = caption.group(1)
                caption_kind = (
                    "table"
                    if label.casefold().startswith("tabel")
                    else "chart"
                    if label.casefold().startswith("grafic")
                    else "figure"
                )
                caption_numbers[caption_kind] += 1
            # The address is the first line after the cover's `Sediul` label, in the same cell.
            text = _collapsed(_paragraph_text(paragraph))
            cell = paragraph.getparent()
            seat = cell in seats and bool(text)
            if seat:
                seats.discard(cell)
            if cell is not None and cell.tag == qn("w:tc") and text.rstrip(" :") == "sediul":
                seats.add(cell)
            extent = next(paragraph.iter(_EXTENT), None)
            box = (
                (int(extent.get("cx", "0")), int(extent.get("cy", "0")))
                if extent is not None
                else None
            )
            binding = (
                _binding(section, text, identity, seat)
                if classification == "variable" and not heading
                else None
            )
            if heading:
                item = headings[index]
                title = _TITLES.get(item.section_id)
                if title is not None and not _fixed(section):
                    current = _paragraph_text(paragraph)
                    prefix = _NUMBERED.match(current)
                    text = item.template or title
                    if item.section_id == "ch3.flux":
                        text = title
                    elif item.slots:
                        values = slot_values(text, current)
                        text = re.sub(
                            r"\{([a-z_]+)\}",
                            lambda match, found=values: _heading_slot(
                                match.group(1), found, client_name
                            ),
                            text,
                        )
                    level = (
                        len(prefix.group().strip().rstrip(".").split("."))
                        if prefix
                        else item.heading.level + 1
                    )
                    text = body_title(text, level, current)
                    _set_text(paragraph, (prefix.group() if prefix else "") + text)
                    if MARKER in text:
                        classification = "variable"
                        stamp(paragraph, slot, bookmark_id)
                        bookmark_id += 1
            elif classification == "variable":
                if caption is None:
                    _set_text(paragraph, MARKER)
                else:
                    assert caption_kind is not None
                    _set_text(
                        paragraph,
                        f"{caption.group(1)} {caption_numbers[caption_kind]}. {MARKER}",
                    )
                stamp(paragraph, slot, bookmark_id)
                bookmark_id += 1
            for old in identity:
                _replace_text(paragraph, old, client_name if old == identity[0] else MARKER)
            anchors.append(
                Anchor(
                    slot,
                    section,
                    "word/document.xml",
                    classification,
                    binding,
                    box if binding == "cover_photo" else None,
                )
            )
    for kind, sections_list in (("header", document.sections), ("footer", document.sections)):
        seen: set[int] = set()
        for section in sections_list:
            part = getattr(section, kind)
            root = part._element
            if id(root) in seen:
                continue
            seen.add(id(root))
            for ordinal, paragraph in enumerate(_paragraphs(root)):
                slot = f"{kind}_{len(seen)}_{ordinal}"
                classification, binding = part_classification(paragraph, identity, part.part)
                if classification == "variable" and binding is None:
                    _set_text(paragraph, MARKER)
                if binding == "report_year":
                    for year in set(YEAR.findall(_paragraph_text(paragraph))):
                        _replace_text(paragraph, year, MARKER)
                if classification == "variable":
                    stamp(paragraph, slot, bookmark_id)
                    bookmark_id += 1
                if classification != "variable" or binding is not None:
                    for old in identity:
                        _replace_text(paragraph, old, client_name if old == identity[0] else MARKER)
                anchors.append(
                    Anchor(slot, "header_footer", f"word/{kind}", classification, binding)
                )
    return tuple(anchors)


def save_anchor_map(path: Path, source_hash: str, anchors: tuple[Anchor, ...]) -> None:
    payload = {
        "version": 1,
        "source_sha256": source_hash,
        "anchors": [anchor.__dict__ for anchor in anchors],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def assert_markers(document: Any, anchors: tuple[Anchor, ...]) -> None:
    variable = {f"_ema_{anchor.slot}" for anchor in anchors if anchor.classification == "variable"}
    found: set[str] = set()
    roots = [document.element]
    roots.extend(section.header._element for section in document.sections)
    roots.extend(section.footer._element for section in document.sections)
    for root in roots:
        for node in root.iter(qn("w:bookmarkStart")):
            name = node.get(qn("w:name"), "")
            if name in variable:
                paragraph = node.getparent()
                if paragraph is None or MARKER not in _paragraph_text(paragraph):
                    raise ValueError(f"variable anchor missing marker: {name}")
                found.add(name)
    if found != variable:
        raise ValueError(f"missing variable anchors: {len(variable - found)}")
