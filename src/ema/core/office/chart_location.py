"""Locate chart paragraphs and copy their caption styling."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
from typing import cast

from lxml import etree

from ema.core.office.errors import OfficeError
from ema.core.office.package import REL_CHART, R, relationships, target_part, xml

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def source_paragraph(
    parts: dict[str, bytes], part: str
) -> tuple[str, etree._Element, etree._Element, etree._Element]:
    for owner in (name for name in parts if name.startswith("word/") and name.endswith(".xml")):
        rel = next(
            (
                item
                for item in relationships(parts, owner)
                if item.get("Type") == REL_CHART
                and target_part(owner, item.get("Target", "")) == part
            ),
            None,
        )
        if rel is None:
            continue
        root = xml(parts, owner)
        charts = [
            node
            for node in cast("list[etree._Element]", root.xpath(".//*[local-name()='chart']"))
            if node.get(f"{{{R}}}id") == rel.get("Id")
        ]
        if len(charts) != 1:
            continue
        paragraphs = cast(
            "list[etree._Element]", charts[0].xpath("ancestor::w:p", namespaces={"w": W})
        )
        if len(paragraphs) == 1:
            return owner, root, paragraphs[0], charts[0]
    raise OfficeError("chart_location", f"Chart paragraph not found: {part}")


def cloned_caption(source: etree._Element, caption: str) -> etree._Element:
    paragraph = etree.Element(f"{{{W}}}p")
    properties = source.find(f"{{{W}}}pPr")
    if properties is not None:
        paragraph.append(copy.deepcopy(properties))
    run = etree.SubElement(paragraph, f"{{{W}}}r")
    original_run = source.find(f"{{{W}}}r")
    run_properties = original_run.find(f"{{{W}}}rPr") if original_run is not None else None
    if run_properties is not None:
        run.append(copy.deepcopy(run_properties))
    etree.SubElement(run, f"{{{W}}}t").text = caption
    return paragraph
