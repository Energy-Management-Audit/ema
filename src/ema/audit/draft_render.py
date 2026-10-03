"""Render a checked draft over its section's own region of the base."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import re
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ema.audit.base_anchor import MARKER
from ema.audit.base_units import heading_spans_document
from ema.audit.catalogue import CATALOGUE
from ema.audit.draft_checks import TOKEN, DraftCheck, DraftReview, check_draft
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.section_body import replace_section_body
from ema.core.errors import EmaError
from ema.core.office.blocks import Block, Caption, Missing, Num, Paragraph, Ref, Segment, Table
from ema.core.office.numbers_ro import format_number
from ema.core.review.models import Field


def _value(field: Field) -> str:
    if field.value_type in {"number", "year"}:
        return format_number(
            Decimal(str(field.value)),
            0 if field.value_type == "year" else field.decimals,
            field.unit,
            False if field.value_type == "year" else field.grouping,
        )
    return str(field.value)


def _resolved(text: str, facts: dict[str, Field]) -> str:
    return TOKEN.sub(lambda match: _value(facts[match.group(1)]), text)


def _cell(text: DraftText, location: str, blocked: set[str], facts: dict[str, Field]) -> Segment:
    return Num(None, 0) if location in blocked else _resolved(text.text, facts)


def _paragraph(
    item: DraftText, location: str, issues: tuple[DraftReview, ...], facts: dict[str, Field]
) -> Block:
    relevant = [issue for issue in issues if issue.location == location]
    if any(issue.code != "uncited_sentence" and issue.sentence is None for issue in relevant):
        return Missing(item.kind, MARKER)
    flagged = {issue.sentence if issue.sentence is not None else issue.detail for issue in relevant}
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", item.text) if part.strip()]
    rendered: list[str] = []
    for sentence in sentences:
        value = MARKER if sentence in flagged else _resolved(sentence, facts)
        if value != MARKER or not rendered or rendered[-1] != MARKER:
            rendered.append(value)
    if rendered == [MARKER]:
        return Missing(item.kind, MARKER)
    return Paragraph(item.kind, [" ".join(rendered)])


def draft_blocks(
    draft: SectionDraft, facts: dict[str, Field], issues: tuple[DraftReview, ...]
) -> list[Block]:
    """The section as blocks: a flagged text or cell becomes the marker, a figure a marker."""
    blocked = {issue.location for issue in issues}
    blocks: list[Block] = [
        _paragraph(item, f"paragraph:{index}", issues, facts)
        for index, item in enumerate(draft.paragraphs)
    ]
    for index, table in enumerate(draft.tables):
        ref = f"{draft.section}.{index}"
        caption = _cell(table.caption, f"table:{index}:caption", blocked, facts)
        blocks.append(Caption("caption", "tab", ref, ["Tabelul ", Ref("tab", ref), " ", caption]))
        rows = [
            [
                [_cell(cell, f"table:{index}:{row}:{column}", blocked, facts)]
                for column, cell in enumerate(cells)
            ]
            for row, cells in enumerate(table.rows)
        ]
        header = [MARKER if isinstance(cell[0], Num) else str(cell[0]) for cell in rows[0]]
        blocks.append(Table("table", rows[1:], header_rows=1, header=[header]))
    blocks.extend(Missing("body", MARKER) for _ in draft.figures)
    if draft.status == "missing":
        blocks.append(Missing("body", MARKER))
    return blocks


def _clone_paragraph(prototype: Any, text: str) -> Any:
    cloned = deepcopy(prototype)
    for child in list(cloned):
        if child.tag != qn("w:pPr"):
            cloned.remove(child)
    run = next((item for item in prototype if item.tag == qn("w:r")), None)
    copied_run = deepcopy(run) if run is not None else OxmlElement("w:r")
    for child in list(copied_run):
        if child.tag != qn("w:rPr"):
            copied_run.remove(child)
    value = OxmlElement("w:t")
    value.text = text
    copied_run.append(value)
    cloned.append(copied_run)
    return cloned


def _insert_absent_section(document: Any, section_id: str, spans: list[Any]) -> bool:
    catalogue = {section.id: section for section in CATALOGUE}
    target = catalogue[section_id]
    if target.chapter not in {2, 3} or target.parent is None:
        return False
    if any(item.section_id == section_id for item, _, _ in spans):
        return False
    order = {section.id: index for index, section in enumerate(CATALOGUE)}
    siblings = [
        (item, start, end)
        for item, start, end in spans
        if item.section_id in catalogue and catalogue[item.section_id].parent == target.parent
    ]
    following = next(
        (
            (item, start, end)
            for item, start, end in siblings
            if order[item.section_id] > order[section_id]
        ),
        None,
    )
    preceding = next(
        (
            (item, start, end)
            for item, start, end in reversed(siblings)
            if order[item.section_id] < order[section_id]
        ),
        None,
    )
    sibling = following or preceding
    if sibling is None:
        raise EmaError("draft_prototype", "Secţiunea lipseşte din bază.", section_id)
    body = list(document.element.body)
    _, start, end = sibling
    body_prototype = next(
        (element for element in body[start + 1 : end] if element.tag == qn("w:p")),
        None,
    )
    if body_prototype is None:
        raise EmaError("draft_prototype", "Secţiunea nu are model de paragraf.", section_id)
    anchor_index = following[1] if following else end
    anchor = body[anchor_index]
    anchor.addprevious(_clone_paragraph(body[start], target.title))
    anchor.addprevious(_clone_paragraph(body_prototype, MARKER))
    return True


def render_section(
    base: Path,
    output: Path,
    draft: SectionDraft,
    facts: dict[str, Field],
    flags: tuple[DraftReview, ...],
    *,
    job: str,
) -> DraftCheck:
    """Write the checked draft over the section's own region of the base."""
    if output.resolve() == base.resolve():
        raise ValueError("output must not overwrite audit base")
    check = check_draft(draft, facts, job)
    if check.fatal:
        raise EmaError("draft_invalid", "Redactarea nu a trecut verificările.", draft.section)
    issues = (*check.review, *flags)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as directory:
        source = base
        document = Document(str(base))
        spans = heading_spans_document(document)
        if _insert_absent_section(document, draft.section, spans):
            source = Path(directory) / "with-section.docx"
            document.save(str(source))
        replace_section_body(
            source, output, draft.section, draft_blocks(draft, facts, issues), keep_base=True
        )
    return check


def review_payload(
    draft: SectionDraft, check: DraftCheck, flags: tuple[DraftReview, ...]
) -> dict[str, object]:
    return {
        "section": draft.section,
        "coverage": check.coverage,
        "cited_sentences": check.cited_sentences,
        "total_sentences": check.total_sentences,
        "review": [item.__dict__ for item in (*check.review, *flags)],
    }
