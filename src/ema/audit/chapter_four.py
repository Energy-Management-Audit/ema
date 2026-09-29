"""Fill the anchored audit base's chapter-four region and refresh its TOC."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document
from lxml import etree

from ema.audit.base_package import package_issues
from ema.audit.base_toc import refresh_toc
from ema.audit.base_units import heading_spans_document
from ema.audit.catalogue import CATALOGUE
from ema.audit.chapter_four_blocks import chapter_four_blocks
from ema.audit.chapter_four_chart_placement import place_chart_groups
from ema.audit.chapter_four_charts import STYLE_PART, chapter_chart_groups
from ema.audit.heading_titles import heading_blocks
from ema.core.errors import EmaError
from ema.core.office.block_text import set_text
from ema.core.office.blocks import ElementLocator, NativeChart, Prototypes, RenderReport
from ema.core.office.chart_blocks import chart_caption_prototype, import_chart_style
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.region import replace_region
from ema.energy_data.factors import FACTORS_2026, FactorTable
from ema.energy_data.model import EnergyDataset

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MONTHS = (
    "Ianuarie",
    "Februarie",
    "Martie",
    "Aprilie",
    "Mai",
    "Iunie",
    "Iulie",
    "August",
    "Septembrie",
    "Octombrie",
    "Noiembrie",
    "Decembrie",
)


def _located(base: Path) -> tuple[int, int, dict[str, int], list[etree._Element]]:
    document = Document(str(base))
    spans = heading_spans_document(document)
    positions = {item.section_id: start for item, start, _ in spans}
    chapter = positions.get("ch4")
    following = positions.get("ch5", positions.get("ch6"))
    if chapter is None or following is None or following <= chapter:
        raise ValueError("audit base lacks a bounded chapter-four region")
    parts = read_parts(base)
    root = xml(parts, "word/document.xml")
    body = root.find(W + "body")
    if body is None:
        raise ValueError("audit base lacks document body")
    return chapter, following, positions, list(body)


def _table_proto(source: etree._Element, first: int) -> etree._Element:
    result = deepcopy(source)
    rows = result.findall(W + "tr")
    if not rows:
        raise ValueError("chapter-four table prototype has no header")
    cells = rows[0].findall(W + "tc")
    if len(cells) != 7:
        raise ValueError("chapter-four table prototype needs six month columns")
    for cell, title in zip(cells, ("Anul", *MONTHS[first - 1 : first + 5]), strict=True):
        set_text(cell, title)
    return result


def _prototypes(
    positions: dict[str, int], body: list[etree._Element], chapter: int, following: int
) -> Prototypes:
    electric = positions.get("ch4.electricitate")
    if electric is None:
        raise EmaError(
            "heading_prototype_missing",
            "Prototipul titlului secţiunii lipseşte.",
            "ch4.electricitate",
        )
    table = next(
        (body[index] for index in range(electric + 1, following) if body[index].tag == W + "tbl"),
        None,
    )
    caption = next(
        (
            body[index]
            for index in range(electric + 1, following)
            if body[index].tag == W + "p"
            and re.match(
                r"^\s*Tabel", "".join(node.text or "" for node in body[index].iter(W + "t"))
            )
        ),
        None,
    )
    paragraph = next(
        (body[index] for index in range(electric + 1, following) if body[index].tag == W + "p"),
        None,
    )
    if table is None or caption is None or paragraph is None:
        raise ValueError("audit base lacks chapter-four block prototypes")
    elements = {
        "body": paragraph,
        "caption": caption,
        "months_first": _table_proto(table, 1),
        "months_second": _table_proto(table, 7),
    }
    siblings = {
        "ch4.electricitate_pv": "ch4.electricitate",
        "ch4.echiv_pv": "ch4.echiv_electric",
        "ch4.specific_pv": "ch4.specific_electric",
        "ch4.bilant_real": "ch4.mediu",
    }
    for section in CATALOGUE:
        if not section.id.startswith("ch4."):
            continue
        prototype = positions.get(section.id, positions.get(siblings.get(section.id, "")))
        if prototype is None:
            raise EmaError(
                "heading_prototype_missing",
                "Prototipul titlului secţiunii lipseşte.",
                siblings.get(section.id, section.id),
            )
        elements["heading:" + section.id] = body[prototype]
    return Prototypes(elements, 4)


def render_chapter_four(  # noqa: PLR0913
    base: Path,
    output: Path,
    dataset: EnergyDataset,
    base_identity: tuple[str, ...],
    *,
    chart_source: Path,
    client: str,
    factors: FactorTable = FACTORS_2026,
    texts: Mapping[str, str] | None = None,
) -> tuple[RenderReport, list[str]]:
    """Write all catalogue ch. 4 sections using S7 blocks and sourced values."""
    if not dataset.carriers or not dataset.years:
        raise ValueError("chapter four needs located carrier readings and years")
    if not base_identity:
        raise ValueError("base identity denylist is required")
    chapter, following, positions, body = _located(base)
    groups, skipped = chapter_chart_groups(dataset, factors, client)
    blocks = place_chart_groups(chapter_four_blocks(dataset, factors, texts=texts), groups)
    prototypes = _prototypes(positions, body, chapter, following)
    blocks = heading_blocks(blocks, prototypes)
    with TemporaryDirectory() as directory:
        working = base
        end = following + 1
        if groups:
            working = Path(directory) / "chart-style.docx"
            parts = read_parts(base)
            style_part, drawing = import_chart_style(chart_source, parts)
            root = xml(parts, "word/document.xml")
            parent = root.find(W + "body")
            assert parent is not None
            parent.insert(chapter + 1, drawing)
            parts["word/document.xml"] = encoded(root)
            write_parts(parts, working)
            prototypes.elements.update(
                chart=drawing, chart_caption=chart_caption_prototype(chart_source)
            )
            blocks = [
                replace(block, part=style_part)
                if isinstance(block, NativeChart) and block.part == STYLE_PART
                else block
                for block in blocks
            ]
            end += 1
        report = replace_region(
            working,
            output,
            ElementLocator(chapter + 1),
            ElementLocator(end),
            blocks,
            prototypes,
        )
    document = Document(str(output))
    refresh_toc(document)
    document.save(str(output))
    issues = package_issues(output, base_identity)
    if issues:
        output.unlink(missing_ok=True)
        raise ValueError("chapter-four package invalid: " + "; ".join(issues[:8]))
    return report, skipped
