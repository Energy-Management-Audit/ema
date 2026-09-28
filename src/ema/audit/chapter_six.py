"""Chapter 6 measure tables rendered from reviewed, sourced facts."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document
from lxml import etree
from pydantic import BaseModel

from ema.audit.base_anchor import MARKER
from ema.audit.base_package import package_issues
from ema.audit.base_toc import refresh_toc
from ema.audit.base_units import heading_spans_document
from ema.audit.chapter_four_blocks import _written
from ema.core.office.block_text import set_text
from ema.core.office.blocks import (
    Block,
    BulletList,
    Caption,
    ElementLocator,
    Missing,
    Num,
    Paragraph,
    Prototypes,
    Ref,
    RenderReport,
    Retained,
    Segment,
    Table,
)
from ema.core.office.numbers_ro import format_number
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.region import replace_region

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class PlannedMeasure(BaseModel):
    title: str
    effect: str | None
    saving_tep: float | None
    co2_t: float | None
    investment_thousand_lei: float | None
    payback_years: float | None
    cost_note: str | None
    narrative: str | None


class ChapterSixPlan(BaseModel):
    company_name: str | None
    measures: tuple[PlannedMeasure, ...]
    closing: str | None = None


# Her column labels, read from the base's first chapter-six tables.
MEASURE_HEADER = (
    ("Măsuri propuse", "Efect", "Economie de energie", "Investiţie", "Durată recuperare"),
    ("", "", "tep/an", "t CO2", "mii lei", "ani"),
)
SYNTHESIS_HEADER = (
    ("Măsuri propuse", "Economie de energie", "Investiţie", "Durată recuperare"),
    ("", "tep/an", "t CO2", "mii lei", "ani"),
)


def _text(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t")).strip()


def _first_table(body: list[etree._Element], start: int, end: int) -> int:
    return next(index for index in range(start, end) if body[index].tag == W + "tbl")


def _first_paragraph(body: list[etree._Element], start: int, end: int, prefix: str) -> int:
    return next(
        index
        for index in range(start, end)
        if body[index].tag == W + "p" and _text(body[index]).startswith(prefix)
    )


def _layout(base: Path) -> tuple[int, int, int, Prototypes, list[Block]]:
    document = Document(str(base))
    spans = heading_spans_document(document)
    positions = {item.section_id: start for item, start, _ in spans}
    start = positions.get("ch6.specifice")
    following = positions.get("ch7")
    measure = next((start for item, start, _ in spans if item.section_id == "ch6.measure"), None)
    synthesis = positions.get("ch6.sinteza")
    if None in (start, following, measure, synthesis):
        raise ValueError("audit base lacks chapter-six measures or synthesis")
    assert (
        start is not None
        and following is not None
        and measure is not None
        and synthesis is not None
    )
    chapter = 6 if "ch5" in positions else 5
    parts = read_parts(base)
    root = xml(parts, "word/document.xml")
    body_node = root.find(W + "body")
    if body_node is None:
        raise ValueError("audit base lacks document body")
    body = list(body_node)
    first_table = _first_table(body, measure, synthesis)
    synthesis_table = _first_table(body, synthesis, following)
    caption = _first_paragraph(body, measure, first_table, "Tabelul")
    synth_caption = _first_paragraph(body, synthesis, synthesis_table, "Tabelul")
    synthesis_intro = next(
        index
        for index in range(synthesis + 1, synth_caption)
        if body[index].tag == W + "p" and _text(body[index])
    )
    bullet = next(
        index
        for index in range(start + 1, measure)
        if body[index].tag == W + "p" and body[index].find(".//" + W + "pStyle") is not None
    )
    # De-identified bases replace the old prose with a marker, but keep its paragraph style.
    prose = caption - 1
    elements = {
        "intro": body[start + 1],
        "bullet": body[bullet],
        "measure_heading": body[measure],
        "body": body[prose],
        "caption": body[caption],
        "table_title": body[caption + 1],
        "measure_table": body[first_table],
        "synthesis_heading": body[synthesis],
        "synthesis_intro": body[synthesis_intro],
        "synthesis_caption": body[synth_caption],
        "synthesis_title": body[synth_caption + 1],
        "synthesis_table": body[synthesis_table],
    }
    # Her closing prose gives way to the reviewed text; empty and layout paragraphs stay.
    closing: list[Block] = []
    for index in range(synthesis_table + 1, following):
        if _text(body[index]):
            elements.setdefault("closing", body[index])
            continue
        key = f"closing:{index}"
        elements[key] = body[index]
        closing.append(Retained(key))
    elements.setdefault("closing", body[prose])
    return start, following, chapter, Prototypes(elements, chapter, MARKER), closing


def _number(value: float | None, decimals: int) -> list[Segment]:
    if value is None:
        return [Num(None, decimals)]
    formatted = format_number(value, decimals)
    if "," in formatted:
        formatted = formatted.rstrip("0").rstrip(",")
    return [formatted]


def _measure_row(item: PlannedMeasure) -> list[list[Segment]]:
    return [
        [item.title],
        [item.effect] if item.effect is not None else [Num(None, 0)],
        _number(item.saving_tep, 2),
        _number(item.co2_t, 2),
        _number(item.investment_thousand_lei, 2),
        _number(item.payback_years, 1),
    ]


def _synthesis_row(item: PlannedMeasure) -> list[list[Segment]]:
    row = _measure_row(item)
    return [row[0], *row[2:]]


def _blocks(plan: ChapterSixPlan, closing: list[Block]) -> list[Block]:
    company: list[str | Num] = [plan.company_name] if plan.company_name else [Num(None, 0)]
    blocks: list[Block] = [
        Paragraph(
            "intro",
            [
                "Măsurile de creștere a eficienței energetice propuse "
                "spre implementare la nivelul ",
                *company,
                " sunt:",
            ],
        ),
        BulletList(
            "bullet",
            [
                [
                    item.title[:1].lower()
                    + item.title[1:]
                    + ("." if index == len(plan.measures) - 1 else ";")
                ]
                for index, item in enumerate(plan.measures)
            ],
        ),
    ]
    for index, item in enumerate(plan.measures, 1):
        ref = f"ch6.measure.{index}"
        blocks.append(Paragraph("measure_heading", [item.title]))
        blocks.append(
            Paragraph("body", [item.narrative]) if item.narrative else Missing("body", MARKER)
        )
        blocks.extend(
            (
                Paragraph(
                    "body",
                    [
                        "În tabelul numărul ",
                        Ref("tab", ref),
                        " se prezintă estimarea eficienței energetice care s-ar putea "
                        "obține în urma implementării măsurii propuse.",
                    ],
                ),
                Caption("caption", "tab", ref, ["Tabelul ", Ref("tab", ref)]),
                Paragraph(
                    "table_title",
                    ["Sinteza măsurii de eficiență energetică propusă pentru implementare"],
                ),
                Table(
                    "measure_table",
                    [_measure_row(item)],
                    header_rows=2,
                    header=[list(row) for row in MEASURE_HEADER],
                ),
                Paragraph(
                    "body",
                    [
                        item.cost_note
                        or (
                            "Costurile sunt estimate, iar la implementarea măsurii se recomandă "
                            "să se realizeze un proiect tehnic care să prezinte datele tehnice "
                            "concrete pentru această soluție."
                        )
                    ],
                ),
            )
        )
    ref = "ch6.sinteza"
    blocks.extend(
        (
            Paragraph(
                "synthesis_heading",
                ["Sinteza măsurilor de eficiență energetică propuse pentru implementare"],
            ),
            Paragraph(
                "synthesis_intro",
                [
                    "Pentru creșterea eficienței energetice a platformei, se propun "
                    "implementarea următoarelor măsuri de creștere a eficienței energetice, "
                    "descrise anterior și centralizate în tabelul ",
                    Ref("tab", ref),
                    ".",
                ],
            ),
            Caption("synthesis_caption", "tab", ref, ["Tabelul ", Ref("tab", ref)]),
            Paragraph(
                "synthesis_title",
                ["Sinteza măsurilor de eficiență energetică propuse pentru implementare"],
            ),
            Table(
                "synthesis_table",
                [_synthesis_row(item) for item in plan.measures],
                header_rows=2,
                header=[list(row) for row in SYNTHESIS_HEADER],
            ),
            *(replace(block, proto="closing") for block in _written(plan.closing)),
            *closing,
        )
    )
    return blocks


def render_chapter_six(
    base: Path, output: Path, plan: ChapterSixPlan, base_identity: tuple[str, ...]
) -> RenderReport:
    if not base_identity:
        raise ValueError("base identity denylist is required")
    start, following, _chapter, prototypes, closing = _layout(base)
    # The block engine checks captions before the old region is removed.
    # Retire only those captions in a temporary copy so its numbering sees the final region.
    with TemporaryDirectory() as directory:
        source = Path(directory) / "chapter-six-source.docx"
        parts = read_parts(base)
        root = xml(parts, "word/document.xml")
        body = root.find(W + "body")
        assert body is not None
        for element in list(body)[start + 1 : following]:
            if element.tag != W + "p" or not _text(element).startswith("Tabelul "):
                continue
            nodes = list(element.iter(W + "t"))
            for index, node in enumerate(nodes):
                node.text = "retired caption" if index == 0 else ""
        if prototypes.chapter == 6:
            for element in list(body)[following:]:
                if element.tag != W + "p":
                    continue
                before = _text(element)
                after = re.sub(
                    r"(?i)^(Tabel(?:ul)?(?:\s+nr\.?)?\s+)6\.",
                    r"\g<1>7.",
                    before,
                    count=1,
                )
                if after != before:
                    set_text(element, after)
        parts["word/document.xml"] = encoded(root)
        write_parts(parts, source)
        report = replace_region(
            source,
            output,
            ElementLocator(start + 1),
            ElementLocator(following + 1),
            _blocks(plan, closing),
            prototypes,
        )
    document = Document(str(output))
    refresh_toc(document)
    document.save(str(output))
    issues = package_issues(output, base_identity)
    if issues:
        output.unlink(missing_ok=True)
        raise ValueError("chapter-six package invalid: " + "; ".join(issues[:8]))
    return report
