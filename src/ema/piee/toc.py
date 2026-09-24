"""Edit authored TOC entries while leaving its compact paragraph spacing intact."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from docx.oxml.ns import qn

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
