"""Render a checked draft over its section's own region of the base."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from ema.audit.base_anchor import MARKER
from ema.audit.draft_checks import TOKEN, DraftCheck, DraftReview, check_draft
from ema.audit.draft_schema import DraftText, SectionDraft
from ema.audit.section_body import replace_section_body
from ema.audit.sections import mark_drafted, recompute_ready
from ema.core.errors import EmaError
from ema.core.office.blocks import Block, Caption, Missing, Num, Paragraph, Ref, Segment, Table
from ema.core.office.numbers_ro import format_number
from ema.core.review.models import Field
from ema.core.workspace import Workspace


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


def draft_blocks(draft: SectionDraft, facts: dict[str, Field], blocked: set[str]) -> list[Block]:
    """The section as blocks: a flagged text or cell becomes the marker, a figure a marker."""
    blocks: list[Block] = [
        Missing(item.kind, MARKER)
        if f"paragraph:{index}" in blocked
        else Paragraph(item.kind, [_resolved(item.text, facts)])
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
    blocked = {issue.location for issue in (*check.review, *flags)}
    output.parent.mkdir(parents=True, exist_ok=True)
    replace_section_body(base, output, draft.section, draft_blocks(draft, facts, blocked))
    return check


def unrendered_items(draft: SectionDraft) -> tuple[str, ...]:
    return tuple(
        [
            f"table:{index}: not rendered yet; S8 table slots required"
            for index in range(len(draft.tables))
        ]
        + [
            f"figure:{index}: not rendered yet; S8 figure slots required"
            for index in range(len(draft.figures))
        ]
    )


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


def mark_section_drafted(ws: Workspace, job: str, draft: SectionDraft) -> None:
    """Capture the exact fact dependency of a drafted section for staleness."""
    if draft.status == "drafted":
        recompute_ready(ws, job)
        keys = {key for paragraph in draft.paragraphs for key in paragraph.fact_ids}
        keys.update(figure.fact_id for figure in draft.figures)
        mark_drafted(ws, job, draft.section, "agent", tuple(f"fact:{key}" for key in sorted(keys)))


def render_draft_section(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    base: Path,
    output: Path,
    *,
    draft: SectionDraft,
    facts: dict[str, Field],
    flags: tuple[DraftReview, ...],
) -> DraftCheck:
    """Publish paragraph output and capture the exact fact dependency for staleness."""
    check = render_section(base, output, draft, facts, flags, job=job)
    review_path = output.with_suffix(".draft-review.json")
    review_path.write_text(
        json.dumps(review_payload(draft, check, flags), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    mark_section_drafted(ws, job, draft)
    return check
