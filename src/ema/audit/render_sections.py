"""What a draft render wrote itself becomes `drafted` by Ema; a final refuses a changed base."""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from ema.audit.catalogue import CATALOGUE
from ema.audit.render_steps import section_ids
from ema.audit.sections import mark_drafted, refresh_staleness, statuses
from ema.core.errors import EmaError
from ema.core.jobs import StageContext
from ema.core.review.section_transition import Status

# Her fixed text, the chapter introductions she writes, and ch. 4, written from reviewed data.
RENDER_DRAFTED = tuple(
    section.id
    for section in CATALOGUE
    if section.kind == "fixed"
    or section.chapter == 4
    or section.id in {"ch3", "ch6", "ch6.indicatori"}
)
_WRITTEN = {"ch3", "ch6", "ch4.concluzii", "ch4.eficienta", "ch4.bilant_real"}


def _fingerprint(section_id: str, base_sha: str) -> tuple[str, ...]:
    text = (f"fact:narrative.{section_id}",) if section_id in _WRITTEN else ()
    return (f"base:{base_sha}", "fact:audit.company_name", *text)


def mark_render_drafted(
    ctx: StageContext, docx: Path, base_sha: str, failed: Collection[str]
) -> list[str]:
    """Mark each present, render-written section `ready -> drafted` (or a stale draft anew).

    ``failed`` names the writers that failed: ``ch4`` stands for every ch. 4 section. The
    render read every section's revision as an input; a mark it makes itself is recorded as
    what it read, so the draft stays current, while any other change still makes it stale.
    """
    ws, job = ctx.ws, ctx.job
    prior = {state.section_id: state.revision for state in statuses(ws, job)}
    refresh_staleness(ws, job, base_sha=base_sha)
    present = set(section_ids(docx))
    marked: list[str] = []
    for state in statuses(ws, job):
        section_id = state.section_id
        if (
            section_id not in RENDER_DRAFTED
            or section_id not in present
            or section_id in failed
            or (section_id.startswith("ch4") and "ch4" in failed)
            or not (
                state.status == Status.READY or (state.status == Status.DRAFTED and state.stale)
            )
        ):
            continue
        after = mark_drafted(
            ws, job, section_id, "ema", _fingerprint(section_id, base_sha), detail="audit_render"
        )
        read = ("section_states", f"{job}:{section_id}")
        if ctx.reads.get(read) == prior[section_id]:
            ctx.reads[read] = after.revision
        marked.append(section_id)
    return marked


def refuse_changed_base(ctx: StageContext, base_sha: str) -> None:
    """A final written from another base than the one its sections were confirmed on fails."""
    with ctx.ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        refresh_staleness(ctx.ws, ctx.job, db, base_sha=base_sha)
        changed = [
            state.section_id
            for state in statuses(ctx.ws, ctx.job, db)
            if state.stale and (state.changed_input or "").startswith("base:")
        ]
    if changed:
        raise EmaError(
            "base_changed", "Baza raportului s-a schimbat. Refaceţi ciorna.", ",".join(changed)
        )
