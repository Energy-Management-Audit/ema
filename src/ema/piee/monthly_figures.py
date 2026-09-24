"""Remove unavailable PV figures with their captions and observations."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchors import AnchorLedger, find
from ema.core.office.base_map import BaseMap
from ema.core.office.bookmark_region import remove_following
from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.piee.chart_plan import BINDINGS, chart_series
from ema.piee.dataset import PieeData

PV_FIGURES = ((9, 120, 124), (10, 125, 129), (11, 130, 134))


@dataclass(frozen=True)
class FigureGroup:
    chart_number: int
    first_slot: str
    last_slot: str
    year_offset: int


def build_figure_groups(parts: dict[str, bytes], mapping: BaseMap, output: Path) -> None:
    body = xml(parts, "word/document.xml").find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    slots = {entry.selector: entry.slot for entry in mapping.elements if entry.kind == "paragraph"}
    groups: list[FigureGroup] = []
    for chart_number, start, end in PV_FIGURES:
        endpoints = [
            slots.get(list(body)[index - 1].getroottree().getelementpath(list(body)[index - 1]))
            for index in (start, end)
        ]
        if any(slot is None for slot in endpoints):
            raise ValueError(f"PV figure {chart_number} lacks bookmarked boundaries")
        groups.append(
            FigureGroup(chart_number, str(endpoints[0]), str(endpoints[1]), chart_number - 11)
        )
    output.write_text(json.dumps([asdict(item) for item in groups]), encoding="utf-8")


def render_missing_monthly_figures(
    source: Path, manifest: Path, data: PieeData, output: Path, ledger: AnchorLedger
) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    for raw in json.loads(manifest.read_text(encoding="utf-8")):
        group = FigureGroup(**raw)
        binding = next(x for x in BINDINGS if x.slot == f"chart_{group.chart_number}")
        if chart_series(data, binding)[0] is not None:
            continue
        first = find([root], group.first_slot)
        last = find([root], group.last_slot)
        remove_following(first, last, ledger)
        set_paragraph_text(
            first,
            f"Anul {data.year + group.year_offset}: date lunare indisponibile.",
            missing=True,
        )
        ledger.record(group.first_slot)
        if group.chart_number == 11:
            following = first.getnext()
            spacer = etree.Element(qn("w:p"))
            properties = following.find(qn("w:pPr")) if following is not None else None
            if properties is not None:
                spacer.append(copy.deepcopy(properties))
            parent = first.getparent()
            if parent is None:
                raise ValueError("missing PV figure has no parent")
            parent.insert(parent.index(first) + 1, spacer)
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
