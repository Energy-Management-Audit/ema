"""Render checked narrative into existing paragraph anchors only."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import cast

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

from ema.audit.base_anchor import MARKER
from ema.audit.draft_checks import TOKEN, DraftCheck, DraftReview, check_draft
from ema.audit.draft_schema import SectionDraft
from ema.audit.sections import mark_drafted, recompute_ready
from ema.core.errors import EmaError
from ema.core.office.anchors import find
from ema.core.office.block_text import set_text
from ema.core.office.numbers_ro import format_number
from ema.core.review.models import Field
from ema.core.workspace import Workspace


def _value(field: Field) -> str:
    if field.value_type in {"number", "year"}:
        raw = str(field.value)
        decimals = len(raw.partition(".")[2]) if field.value_type == "number" else 0
        return format_number(cast(float, Decimal(raw)), decimals, field.unit)
    return str(field.value)


def _resolved(text: str, facts: dict[str, Field]) -> str:
    return TOKEN.sub(lambda match: _value(facts[match.group(1)]), text)


def _writable(document: etree._Element, slot: str) -> etree._Element | None:
    element = find([document], slot)
    if any(parent.tag == qn("w:tbl") for parent in element.iterancestors()):
        return None
    properties = element.find(qn("w:pPr"))
    style = properties.find(qn("w:pStyle")) if properties is not None else None
    style_name = style.get(qn("w:val"), "").casefold() if style is not None else ""
    if style_name.startswith(("heading", "titlu")) or (
        properties is not None and properties.find(qn("w:outlineLvl")) is not None
    ):
        return None
    content = "".join(node.text or "" for node in element.iter(qn("w:t"))).strip()
    if content.startswith(("Tabel", "Fig.", "Figura", "Grafic")):
        return None
    return element


def render_section(  # noqa: PLR0913
    base: Path,
    anchors: Path,
    output: Path,
    draft: SectionDraft,
    facts: dict[str, Field],
    flags: tuple[DraftReview, ...],
    *,
    job: str,
) -> DraftCheck:
    """Replace only this section's paragraph bookmarks; defer non-paragraph slots."""
    if output.resolve() == base.resolve():
        raise ValueError("output must not overwrite audit base")
    check = check_draft(draft, facts, job)
    if check.fatal:
        raise EmaError("draft_invalid", "Redactarea nu a trecut verificările.", draft.section)
    blocked = {issue.location for issue in (*check.review, *flags)}
    mapping = json.loads(anchors.read_text(encoding="utf-8"))
    if mapping.get("version") != 1:
        raise ValueError("unsupported audit anchor map")
    document = Document(str(base))
    slots = [
        item["slot"]
        for item in mapping["anchors"]
        if item["section"] == draft.section
        and item["classification"] == "variable"
        and item["part"] == "word/document.xml"
    ]
    writable = [
        element for slot in slots if (element := _writable(document.element, slot)) is not None
    ]
    paragraphs = [
        MARKER if f"paragraph:{index}" in blocked else _resolved(item.text, facts)
        for index, item in enumerate(draft.paragraphs)
    ]
    if draft.status == "missing":
        paragraphs.append(MARKER)
    if len(paragraphs) > len(writable):
        raise EmaError(
            "draft_slots", "Secțiunea nu are suficiente ancore de paragraf.", draft.section
        )
    for element, text in zip(writable, paragraphs, strict=False):
        set_text(element, text, missing=text == MARKER)
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output))
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
    anchors: Path,
    output: Path,
    *,
    draft: SectionDraft,
    facts: dict[str, Field],
    flags: tuple[DraftReview, ...],
) -> DraftCheck:
    """Publish paragraph output and capture the exact fact dependency for staleness."""
    check = render_section(base, anchors, output, draft, facts, flags, job=job)
    review_path = output.with_suffix(".draft-review.json")
    review_path.write_text(
        json.dumps(review_payload(draft, check, flags), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    mark_section_drafted(ws, job, draft)
    return check
