"""Keep both water headings and show explicit gaps when monthly data is absent."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import json
from pathlib import Path

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchors import AnchorLedger, find
from ema.core.office.bookmark_region import remove_following
from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.energy_data.carriers import Carrier
from ema.piee.dataset import PieeData

INDUSTRIAL_BOOKMARK = "_TocEmaWaterIndustrial"


def _has_water(data: PieeData, carrier: Carrier) -> bool:
    if any(
        series.annual is not None and series.annual.value is not None
        for series in data.dataset.carriers.get(carrier, {}).values()
    ):
        return True
    block = data.necesar.water.get(carrier)
    return bool(
        block
        and any(
            value.total is not None
            and isinstance(value.total.value, int | float)
            and value.total.value > 0
            for value in block.years.values()
        )
    )


def water_missing(data: PieeData) -> bool:
    return not (
        _has_water(data, Carrier.water_potable)
        or _has_water(data, Carrier.water_industrial)
        or _has_water(data, Carrier.water_storm)
    )


def _clone(paragraph: etree._Element, text: str, *, missing: bool) -> etree._Element:
    clone = copy.deepcopy(paragraph)
    for bookmark in tuple(clone.iter()):
        if bookmark.tag in {qn("w:bookmarkStart"), qn("w:bookmarkEnd")}:
            parent = bookmark.getparent()
            if parent is not None:
                parent.remove(bookmark)
    set_paragraph_text(clone, text, missing=missing)
    return clone


def _bookmark(paragraph: etree._Element, bookmark_id: int, name: str) -> None:
    start = etree.Element(qn("w:bookmarkStart"))
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = etree.Element(qn("w:bookmarkEnd"))
    end.set(qn("w:id"), str(bookmark_id))
    paragraph.insert(1 if paragraph.find(qn("w:pPr")) is not None else 0, start)
    paragraph.append(end)


def render_missing_water(
    source: Path, data: PieeData, section_manifest: Path, output: Path, ledger: AnchorLedger
) -> None:
    """Replace absent potable/industrial figures with red lines, leaving their headings."""
    if not water_missing(data):
        output.write_bytes(source.read_bytes())
        return
    groups = json.loads(section_manifest.read_text(encoding="utf-8"))
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    start = find([root], groups["water"][0])
    end = find([root], groups["water"][1])
    introduction = find([root], "body_237")
    period = f"{data.year - 2} – {data.year}"
    missing = f"Date indisponibile pentru perioada de analiză {period}."
    remove_following(introduction, end, ledger)
    set_paragraph_text(introduction, missing, missing=True)
    ledger.record("body_237")
    body = start.getparent()
    assert body is not None
    position = body.index(introduction)
    industrial = _clone(start, "Analiza consumului de apă industrială", missing=False)
    ids = [int(node.get(qn("w:id"), "0")) for node in root.iter(qn("w:bookmarkStart"))]
    _bookmark(industrial, max(ids, default=0) + 1, INDUSTRIAL_BOOKMARK)
    body.insert(position + 1, industrial)
    body.insert(position + 2, _clone(introduction, missing, missing=True))
    ledger.record(groups["water"][0])
    specific_start = find([root], groups["specific_water"][0])
    specific_end = find([root], groups["specific_water"][1])
    specific_intro = find([root], "body_343")
    if specific_start.getparent() is not specific_intro.getparent():
        raise ValueError("specific water heading moved")
    remove_following(specific_intro, specific_end, ledger)
    set_paragraph_text(specific_intro, f"Apă potabilă: {missing}", missing=True)
    ledger.record("body_343")
    parent = specific_intro.getparent()
    assert parent is not None
    parent.insert(
        parent.index(specific_intro) + 1,
        _clone(specific_intro, f"Apă industrială: {missing}", missing=True),
    )
    ledger.record(groups["specific_water"][0])
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
