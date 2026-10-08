"""Fill the anchored audit base's chapter-four region and refresh its TOC."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
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
from ema.audit.chapter_four_format import format_chapter_four
from ema.audit.chapter_four_water import without_empty_water
from ema.audit.heading_titles import heading_blocks
from ema.core.errors import EmaError
from ema.core.office.block_text import set_text
from ema.core.office.blocks import ElementLocator, NativeChart, Prototypes, RenderReport
from ema.core.office.chart_blocks import chart_caption_prototype, import_chart_style
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.region import replace_region
from ema.energy_data.factors import AUDIT_FACTORS_2026, FactorTable
from ema.energy_data.model import EnergyDataset

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FACTOR_LEAD_IN = "s-au utilizat următorii factori de emisii"
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


def _emissions_proto(source: etree._Element, years: tuple[int, ...]) -> etree._Element:
    """The month table cut to a source column and one column per year, at the same width."""
    result = deepcopy(source)
    keep = 1 + len(years)
    rows = result.findall(W + "tr")
    if not 2 <= keep <= len(rows[0].findall(W + "tc")):
        raise ValueError("emissions table needs one to six years")
    for row in rows:
        cells = row.findall(W + "tc")
        for cell in cells[keep:]:
            row.remove(cell)
        width = sum(int(w.get(W + "w", "0")) for c in cells for w in c.iter(W + "tcW"))
        for cell in cells[:keep]:
            for node in cell.iter(W + "tcW"):
                node.set(W + "w", str(width // keep))
    grid = result.find(W + "tblGrid")
    if grid is not None:
        columns = grid.findall(W + "gridCol")
        total = sum(int(column.get(W + "w", "0")) for column in columns)
        for column in columns[keep:]:
            grid.remove(column)
        for column in columns[:keep]:
            column.set(W + "w", str(total // keep))
    return result


def factor_notes(source: Path) -> list[etree._Element]:
    """Her fixed lead-in and bullets naming the emission factors, as authored in the source."""
    body = xml(read_parts(source), "word/document.xml").find(W + "body")
    if body is None:
        return []
    paragraphs = [item for item in body if item.tag == W + "p"]
    start = next(
        (i for i, item in enumerate(paragraphs) if FACTOR_LEAD_IN in _text(item)), len(paragraphs)
    )
    notes: list[etree._Element] = []
    for item in paragraphs[start:]:
        if not _text(item).strip():
            break
        note = deepcopy(item)
        _unlink(note)
        notes.append(note)
    return notes


def _unlink(paragraph: etree._Element) -> None:
    """Keep a URL as plain text: a link field or hyperlink would need a relationship."""
    for link in list(paragraph.iter(W + "hyperlink")):
        parent = link.getparent()
        assert parent is not None
        index = parent.index(link)
        for run in list(link):
            parent.insert(index, run)
            index += 1
        parent.remove(link)
    for run in list(paragraph.iter(W + "r")):
        if run.find(W + "fldChar") is not None or run.find(W + "instrText") is not None:
            parent = run.getparent()
            assert parent is not None
            parent.remove(run)


def _text(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def _prototypes(
    positions: dict[str, int],
    body: list[etree._Element],
    chapter: int,
    following: int,
    years: tuple[int, ...],
    notes: Sequence[etree._Element] = (),
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
    # Her chapter's own list paragraph for the annual and factor lists; a body one without.
    headings = set(positions.values())
    bullet = next(
        (
            body[index]
            for index in range(chapter + 1, following)
            if index not in headings
            and body[index].tag == W + "p"
            and body[index].find(f".//{W}numPr") is not None
        ),
        paragraph,
    )
    elements = {
        "body": paragraph,
        "bullet": bullet,
        "caption": caption,
        "months_first": _table_proto(table, 1),
        "months_second": _table_proto(table, 7),
        "emissions": _emissions_proto(table, years),
        **{f"emission_note:{i}": note for i, note in enumerate(notes)},
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
    factors: FactorTable = AUDIT_FACTORS_2026,
    texts: Mapping[str, str] | None = None,
) -> tuple[RenderReport, list[str]]:
    """Write all catalogue ch. 4 sections using S7 blocks and sourced values."""
    if not dataset.carriers or not dataset.years:
        raise ValueError("chapter four needs located carrier readings and years")
    if not base_identity:
        raise ValueError("base identity denylist is required")
    chapter, following, positions, body = _located(base)
    dataset = without_empty_water(dataset)
    groups, skipped = chapter_chart_groups(dataset, factors, client)
    notes = factor_notes(chart_source)
    blocks = place_chart_groups(
        chapter_four_blocks(
            dataset, factors, texts=texts, client=client, notes=tuple(_text(n) for n in notes)
        ),
        groups,
    )
    prototypes = _prototypes(positions, body, chapter, following, dataset.years, notes)
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
    format_chapter_four(document, missing_text=prototypes.missing_text)
    refresh_toc(document)
    document.save(str(output))
    issues = package_issues(output, base_identity)
    if issues:
        output.unlink(missing_ok=True)
        raise ValueError("chapter-four package invalid: " + "; ".join(issues[:8]))
    return report, skipped
