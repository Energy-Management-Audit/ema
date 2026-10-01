"""Edit authored TOC entries while leaving its compact paragraph spacing intact."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchors import find
from ema.core.office.base_map import BaseMap
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.run_range import TextSpan, replace_spans, visible_text
from ema.piee.water import INDUSTRIAL_BOOKMARK


@dataclass(frozen=True)
class TocManifest:
    water_slot: str
    equivalent_slot: str
    water_heading_end: int
    equivalent_number_end: int
    number_slots: tuple[str, ...]


def build_toc_manifest(parts: dict[str, bytes], mapping: BaseMap, output: Path) -> None:
    root = xml(parts, "word/document.xml")
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    toc = list(body)[1]
    paragraphs = list(toc.iter(qn("w:p")))
    if len(paragraphs) < 27:
        raise ValueError("PIEE base TOC entries changed")
    slots = {entry.selector: entry.slot for entry in mapping.elements if entry.kind == "paragraph"}
    water, equivalent = paragraphs[13], paragraphs[14]
    water_slot = slots.get(water.getroottree().getelementpath(water))
    equivalent_slot = slots.get(equivalent.getroottree().getelementpath(equivalent))
    if water_slot is None or equivalent_slot is None:
        raise ValueError("water TOC entries lack bookmarks")
    water_text, equivalent_text = visible_text(water), visible_text(equivalent)
    page = re.search(r"\d+$", water_text)
    number = re.match(r"2\.2\.6\.", equivalent_text)
    if page is None or number is None:
        raise ValueError("water TOC field structure changed")
    number_slots = tuple(
        str(slot)
        for paragraph in paragraphs
        if (slot := slots.get(paragraph.getroottree().getelementpath(paragraph))) is not None
        and slot.startswith("number_")
    )
    output.write_text(
        json.dumps(
            asdict(
                TocManifest(
                    water_slot,
                    equivalent_slot,
                    page.start(),
                    number.end(),
                    number_slots,
                )
            )
        ),
        encoding="utf-8",
    )


def render_toc(source: Path, manifest: Path, output: Path, *, water_missing: bool) -> None:
    if not water_missing:
        output.write_bytes(source.read_bytes())
        return
    plan = TocManifest(**json.loads(manifest.read_text(encoding="utf-8")))
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    if not any(
        node.get(qn("w:name")) == INDUSTRIAL_BOOKMARK for node in root.iter(qn("w:bookmarkStart"))
    ):
        raise ValueError("industrial water heading bookmark missing")
    water = find([root], plan.water_slot)
    equivalent = find([root], plan.equivalent_slot)
    clone = copy.deepcopy(water)
    for node in tuple(clone.iter()):
        if node.tag in {qn("w:bookmarkStart"), qn("w:bookmarkEnd")}:
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
    replace_spans(
        clone,
        (
            TextSpan(
                0,
                plan.water_heading_end,
                "2.2.6.Analiza consumului de apă industrială",
            ),
        ),
    )
    links = list(clone.iter(qn("w:hyperlink")))
    fields = list(clone.iter(qn("w:instrText")))
    if len(links) != 1 or len(fields) != 1:
        raise ValueError("water TOC hyperlink field changed")
    links[0].set(qn("w:anchor"), INDUSTRIAL_BOOKMARK)
    fields[0].text = f" PAGEREF {INDUSTRIAL_BOOKMARK} \\h "
    parent = water.getparent()
    if parent is None or parent is not equivalent.getparent():
        raise ValueError("water TOC entries separated")
    parent.insert(parent.index(water) + 1, clone)
    replace_spans(
        equivalent,
        (TextSpan(0, plan.equivalent_number_end, "2.2.7."),),
    )
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)


def render_toc_from_headings(  # noqa: C901, PLR0912, PLR0915
    source: Path, output: Path
) -> None:
    """Keep the authored TOC fields while matching its level-three entries to headings."""
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE body is missing")
    sections = list(body)
    toc = sections[1]
    entries = list(toc.iter(qn("w:p")))
    if len(entries) < 25:
        raise ValueError("PIEE TOC structure changed")

    def level(paragraph: etree._Element) -> str:
        properties = paragraph.find(qn("w:pPr"))
        style = properties.find(qn("w:pStyle")) if properties is not None else None
        return style.get(qn("w:val"), "") if style is not None else ""

    headings = [node for node in sections if node.tag == qn("w:p")]
    heading_three = [node for node in headings if level(node) == "Heading3"]
    equivalent = next(
        (
            node
            for node in heading_three
            if "echivalent de energie" in visible_text(node).casefold()
        ),
        None,
    )
    if equivalent is None:
        raise ValueError("equivalent-energy heading missing")
    specific_group = next(
        (
            node
            for node in headings
            if level(node) == "Heading2" and sections.index(node) > sections.index(equivalent)
        ),
        None,
    )
    if specific_group is None:
        raise ValueError("specific-consumption group heading missing")
    first_energy = next(
        (node for node in heading_three if sections.index(node) < sections.index(equivalent)),
        None,
    )
    if first_energy is None:
        raise ValueError("carrier heading missing")
    energy = [
        node
        for node in heading_three
        if sections.index(first_energy) <= sections.index(node) <= sections.index(equivalent)
    ]
    following_heading_one = next(
        (
            node
            for node in headings
            if level(node) == "Heading1" and sections.index(node) > sections.index(specific_group)
        ),
        None,
    )
    end = (
        sections.index(following_heading_one)
        if following_heading_one is not None
        else len(sections)
    )
    specific = [
        node
        for node in heading_three
        if sections.index(specific_group) < sections.index(node) < end
    ]

    bookmark_id = (
        max(
            (int(node.get(qn("w:id"), "0")) for node in root.iter(qn("w:bookmarkStart"))),
            default=0,
        )
        + 1
    )
    for group, start, stop, template, prefix in (
        (energy, 9, 16, entries[9], "2.2"),
        (specific, 16, 26, entries[16], "2.3"),
    ):
        parent = entries[start].getparent()
        if parent is None:
            raise ValueError("TOC entry has no parent")
        position = parent.index(entries[start])
        for entry in entries[start:stop]:
            if entry.getparent() is not parent:
                raise ValueError("TOC entries separated")
            parent.remove(entry)
        for ordinal, heading in enumerate(group, 1):
            target = next(
                (
                    mark.get(qn("w:name"))
                    for mark in heading.iter(qn("w:bookmarkStart"))
                    if (mark.get(qn("w:name")) or "").startswith("_Toc")
                ),
                None,
            )
            if target is None:
                target = f"_TocEma{prefix.replace('.', '')}{ordinal}"
                start_mark = etree.Element(qn("w:bookmarkStart"))
                start_mark.set(qn("w:id"), str(bookmark_id))
                start_mark.set(qn("w:name"), target)
                end_mark = etree.Element(qn("w:bookmarkEnd"))
                end_mark.set(qn("w:id"), str(bookmark_id))
                bookmark_id += 1
                heading.insert(1 if heading.find(qn("w:pPr")) is not None else 0, start_mark)
                heading.append(end_mark)
            clone = copy.deepcopy(template)
            for mark in tuple(clone.iter()):
                if mark.tag in {qn("w:bookmarkStart"), qn("w:bookmarkEnd")}:
                    owner = mark.getparent()
                    if owner is not None:
                        owner.remove(mark)
            content = visible_text(clone)
            page = re.search(r"\d+$", content)
            if page is None:
                raise ValueError("TOC entry has no page field")
            replace_spans(
                clone,
                (TextSpan(0, page.start(), f"{prefix}.{ordinal}.{visible_text(heading)} "),),
            )
            for link in clone.iter(qn("w:hyperlink")):
                link.set(qn("w:anchor"), target)
            for instruction in clone.iter(qn("w:instrText")):
                if "PAGEREF" in (instruction.text or ""):
                    instruction.text = f" PAGEREF {target} \\h "
            parent.insert(position + ordinal - 1, clone)
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
