"""Apply the reviewed S17c corrections once, before de-identifying the base."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from ema.audit.base_numbering import effective_indent, printed_numbers
from ema.audit.base_units import heading_spans_document
from ema.audit.catalogue import CATALOGUE
from ema.core.errors import EmaError

PASTE_SLIP = (
    "Legea nr. 4.180/2002, cu modificările și completările ulterioare"
    "nr. 180/2002, cu modificările și completările ulterioare."
)
CORRECT_LAW = "Legea nr. 180/2002, cu modificările și completările ulterioare."
HEADING_INDENTS = {1: None, 2: 426, 3: 720}


def _digest(node: Any) -> str:
    return hashlib.sha256(etree.tostring(node, method="c14n", exclusive=True)).hexdigest()


def _correct_law(document: Any) -> list[str]:
    changes: list[str] = []
    for paragraph in document.element.body.iter(qn("w:p")):
        nodes = list(paragraph.iter(qn("w:t")))
        text = "".join(node.text or "" for node in nodes)
        if PASTE_SLIP not in text:
            continue
        start = text.index(PASTE_SLIP)
        end = start + len(PASTE_SLIP)
        offset = 0
        for node in nodes:
            value = node.text or ""
            left, right = offset, offset + len(value)
            offset = right
            if left < end and right > start:
                node.text = (
                    value[: max(0, start - left)]
                    + (CORRECT_LAW if left <= start < right else "")
                    + value[max(0, end - left) :]
                )
        corrected = text.replace(PASTE_SLIP, CORRECT_LAW)
        before = hashlib.sha256(text.strip().encode()).hexdigest()
        after = hashlib.sha256(corrected.strip().encode()).hexdigest()
        changes.append(f"G1 fixed text: {before} → {after}; {PASTE_SLIP} → {CORRECT_LAW}")
    return changes


def _cover_shape(document: Any) -> list[str]:
    changes: list[str] = []
    section = document.sections[0]
    height = int(section.page_height - section.top_margin - section.bottom_margin)
    for inline in list(document.element.body.iter(qn("wp:inline"))):
        text = "".join(node.text or "" for node in inline.iter(qn("w:t")))
        if text.strip() != "AUDIT ENERGETIC":
            continue
        before = _digest(inline)
        extent = inline.find(qn("wp:extent"))
        if extent is None:
            raise EmaError(
                "cover_extent_missing",
                "Dimensiunile titlului de pe copertă lipsesc.",
                "AUDIT ENERGETIC WordArt has no wp:extent",
            )
        old_cx = int(extent.get("cx"))
        long_edge = min(old_cx, height, 7700000)
        short_edge = int(extent.get("cy"))
        anchor = OxmlElement("wp:anchor")
        for name, value in {
            "distT": "0",
            "distB": "0",
            "distL": "0",
            "distR": "0",
            "simplePos": "0",
            "relativeHeight": "0",
            "behindDoc": "0",
            "locked": "0",
            "layoutInCell": "1",
            "allowOverlap": "1",
        }.items():
            anchor.set(name, value)
        simple = OxmlElement("wp:simplePos")
        simple.set("x", "0")
        simple.set("y", "0")
        anchor.append(simple)
        # DrawingML extents are unrotated; compensate the centre before rotating 90°.
        displacement = (long_edge - short_edge) // 2
        for direction in ("H", "V"):
            position = OxmlElement("wp:position" + direction)
            position.set("relativeFrom", "margin")
            offset = OxmlElement("wp:posOffset")
            offset.text = str(-displacement if direction == "H" else displacement)
            position.append(offset)
            anchor.append(position)
        extent.set("cx", str(long_edge))
        extent.set("cy", str(short_edge))
        for transform in inline.iter(qn("a:xfrm")):
            transform_extent = transform.find(qn("a:ext"))
            if transform_extent is not None:
                transform_extent.set("cx", str(long_edge))
                transform_extent.set("cy", str(short_edge))
        for child in list(inline):
            if child.tag == qn("wp:docPr"):
                anchor.append(OxmlElement("wp:wrapNone"))
            anchor.append(child)
        inline.getparent().replace(inline, anchor)
        changes.append(
            f"C1 WordArt XML: {before} → {_digest(anchor)}; inline → margin anchor, "
            f"cx {old_cx} → {long_edge}, rotated height {long_edge}"
        )
    return changes


def _transport_funding(document: Any) -> list[str]:
    """Cut the transport-sector funding guide the base's own client had: found by its words."""
    body = document.element.body
    changes: list[str] = []
    for start in list(body.iter(qn("w:p"))):
        text = "".join(node.text or "" for node in start.iter(qn("w:t")))
        if start.getparent() is not body or not all(
            word in text for word in ("naval", "aerian", "feroviar")
        ):
            continue
        # the guide runs to the blank paragraph that closes it
        block = [start]
        for follower in start.itersiblings():
            block.append(follower)
            if follower.tag == qn("w:p") and not "".join(
                node.text or "" for node in follower.iter(qn("w:t"))
            ):
                break
        if block[-1].tag != qn("w:p"):
            raise EmaError(
                "funding_block_unbounded",
                "Paragraful despre finanţarea transporturilor nu are sfârşit.",
                "transport funding guide has no closing blank paragraph",
            )
        before = hashlib.sha256(
            "".join("".join(n.text or "" for n in item.iter(qn("w:t"))) for item in block).encode()
        ).hexdigest()
        for item in block:
            body.remove(item)
        changes.append(
            f"G4 fixed text: transport funding guide, {len(block)} paragraphs, {before} → removed"
        )
    return changes


def _sibling_spacing(groups: dict[str, list[Any]]) -> list[str]:
    """A flow section's sub-headings (processes, equipment) share the first one's line spacing."""
    changes: list[str] = []
    for parent, headings in groups.items():
        reference = next(
            (
                h.pPr.find(qn("w:spacing"))
                for h in headings
                if h.pPr.find(qn("w:spacing")) is not None
            ),
            None,
        )
        if reference is None:
            continue
        for heading in headings:
            properties = heading.get_or_add_pPr()
            current = properties.find(qn("w:spacing"))
            if current is not None and _digest(current) == _digest(reference):
                continue
            if current is not None:
                properties.remove(current)
            copied = deepcopy(reference)
            # schema order: spacing sits before ind, jc
            anchor = next(
                (c for c in properties if c.tag in {qn("w:ind"), qn("w:jc"), qn("w:rPr")}), None
            )
            if anchor is None:
                properties.append(copied)
            else:
                anchor.addprevious(copied)
            changes.append(f"G2/G3 {parent} sibling heading spacing: {_digest(copied)}")
    return changes


def _heading_values(properties: Any) -> str:
    indent = properties.find(qn("w:ind"))
    alignment = properties.find(qn("w:jc"))
    left = indent.get(qn("w:left")) if indent is not None else None
    hanging = indent.get(qn("w:hanging")) if indent is not None else None
    jc = alignment.get(qn("w:val")) if alignment is not None else None
    return f"left={left or 'inherited'}, hanging={hanging or 'inherited'}, jc={jc or 'inherited'}"


def clean_base(document: Any) -> list[str]:
    """Return local digest evidence; reference documents and image bytes remain untouched."""
    changes = _correct_law(document) + _cover_shape(document)
    changes.extend(_normalise_headings(document))
    changes.extend(_normalise_fixed_text(document))
    changes.extend(_transport_funding(document))
    numbers = printed_numbers(document)
    groups: dict[str, list[Any]] = {}
    for item, start, _ in heading_spans_document(document):
        paragraph = document.element.body[start]
        label = numbers.get(paragraph)
        if label is None:
            continue
        level = len(label.rstrip(".").split("."))
        if level not in HEADING_INDENTS:
            continue
        if item.section_id in {"ch3.process", "ch3.equipment"}:
            groups.setdefault(".".join(label.split(".")[:2]), []).append(paragraph)
        properties = paragraph.get_or_add_pPr()
        before = _digest(properties)
        old_values = _heading_values(properties)
        old_left, old_hanging = effective_indent(document, paragraph)
        if level > 1:
            properties.get_or_add_jc().set(qn("w:val"), "left")
        if level == 1:
            if properties.ind is not None:
                properties.remove(properties.ind)
        else:
            indent = properties.get_or_add_ind()
            indent.set(qn("w:left"), str(HEADING_INDENTS[level]))
            indent.set(qn("w:hanging"), "360")
            for attribute in ("firstLine", "leftChars", "hangingChars", "firstLineChars"):
                indent.attrib.pop(qn("w:" + attribute), None)
        after = _digest(properties)
        if before != after:
            left, hanging = effective_indent(document, paragraph)
            changes.append(
                f"G2/G3 {item.section_id} heading pPr: {before} → {after}; "
                f"{old_values} → {_heading_values(properties)}; "
                f"effective left {old_left} → {left}, hanging {old_hanging} → {hanging}, "
                f"number position {old_left - old_hanging} → {left - hanging}"
            )
    changes.extend(_sibling_spacing(groups))
    return changes


def _normalise_headings(document: Any) -> list[str]:
    changes: list[str] = []
    for item, start, _ in heading_spans_document(document):
        paragraph = document.element.body[start]
        nodes = list(paragraph.iter(qn("w:t")))
        before = "".join(node.text or "" for node in nodes)
        after = before.translate(str.maketrans("şţŞŢ", "șțȘȚ"))
        if before == after:
            continue
        for node in nodes:
            node.text = (node.text or "").translate(str.maketrans("şţŞŢ", "șțȘȚ"))
        changes.append(
            f"F17 {item.section_id} heading: {hashlib.sha256(before.encode()).hexdigest()} → "
            f"{hashlib.sha256(after.encode()).hexdigest()}; {before} → {after}"
        )
    return changes


def _normalise_fixed_text(document: Any) -> list[str]:
    fixed = {section.id for section in CATALOGUE if section.kind == "fixed"}
    changes: list[str] = []
    for section, start, end in heading_spans_document(document):
        if section.section_id not in fixed:
            continue
        for paragraph in list(document.element.body)[start + 1 : end]:
            nodes = list(paragraph.iter(qn("w:t")))
            before = "".join(node.text or "" for node in nodes)
            after = before.translate(str.maketrans("şţŞŢ", "șțȘȚ"))
            if before == after:
                continue
            for node in nodes:
                node.text = (node.text or "").translate(str.maketrans("şţŞŢ", "șțȘȚ"))
            changes.append(
                f"F17 {section.section_id} fixed text: "
                f"{hashlib.sha256(before.encode()).hexdigest()} → "
                f"{hashlib.sha256(after.encode()).hexdigest()}"
            )
    return changes
