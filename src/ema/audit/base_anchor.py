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

from ema.audit.base_numeric import approved_fixed_number, has_number
from ema.audit.base_units import heading_spans_document
from ema.audit.catalogue import CATALOGUE
from ema.audit.headings import MappedHeading
from ema.core.office.anchors import stamp

MARKER = "[de completat]"
_TITLES = {section.id: section.title for section in CATALOGUE}
_CAPTION = re.compile(r"^\s*(Fig\.|Figura|Tabelul|Tabel|Graficul|Grafic)\s*(?:nr\.?\s*)?\d+", re.I)


@dataclass(frozen=True)
class Anchor:
    slot: str
    section: str
    part: str
    classification: str


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


def _classification(
    section: str, paragraph: Any, identity: tuple[str, ...], *, heading: bool
) -> str:
    properties = paragraph.find(qn("w:pPr"))
    style = properties.find(qn("w:pStyle")) if properties is not None else None
    if style is not None and (style.get(qn("w:val")) or "").startswith("TOC"):
        return "structural"
    if heading:
        return "structural"
    text = _paragraph_text(paragraph).casefold()
    if not text.strip() and next(paragraph.iter(qn("w:drawing")), None) is None:
        return "fixed"
    if (
        section == "front"
        and style is not None
        and not any(term.casefold() in text for term in identity)
        and (not has_number(text) or approved_fixed_number(_paragraph_text(paragraph)))
    ):
        return "fixed"
    if (
        _fixed(section)
        and not any(term.casefold() in text for term in identity)
        and (not has_number(text) or approved_fixed_number(_paragraph_text(paragraph)))
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
                and _classification(section, paragraph, identity, heading=False) == "variable"
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
            classification = _classification(section, paragraph, identity, heading=heading)
            if (
                classification == "fixed"
                and has_number(_paragraph_text(paragraph))
                and not approved_fixed_number(_paragraph_text(paragraph))
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
            if heading:
                item = headings[index]
                title = _TITLES.get(item.section_id)
                if title is not None and not _fixed(section):
                    current = _paragraph_text(paragraph)
                    prefix = re.match(r"^\s*\d+(?:\.\d+)*[.\s-]+", current)
                    template = item.template or title
                    if item.slots:
                        template = re.sub(r"\{[a-z_]+\}", MARKER, template)
                        classification = "variable"
                    _set_text(paragraph, (prefix.group() if prefix else "") + template)
                    if classification == "variable":
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
            anchors.append(Anchor(slot, section, "word/document.xml", classification))
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
                classification = _classification("ch1", paragraph, identity, heading=False)
                if (
                    classification == "fixed"
                    and has_number(_paragraph_text(paragraph))
                    and not approved_fixed_number(_paragraph_text(paragraph))
                ):
                    raise ValueError(f"unlisted fixed number at {kind}_{len(seen)}_{ordinal}")
                if classification == "variable":
                    _set_text(paragraph, MARKER)
                    stamp(paragraph, slot, bookmark_id)
                    bookmark_id += 1
                else:
                    for old in identity:
                        _replace_text(paragraph, old, client_name if old == identity[0] else MARKER)
                anchors.append(Anchor(slot, "header_footer", f"word/{kind}", classification))
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
