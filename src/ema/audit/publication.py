"""Publish section state only from the composition inputs, in the runner's transaction."""

import sqlite3
from collections.abc import Iterable
from typing import Literal

from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import mark_drafted, statuses
from ema.audit.staleness import current_inputs, snapshot_inputs
from ema.core.jobs import StageContext
from ema.core.jobs.fingerprint import collection_revision
from ema.core.jobs.reads import revision
from ema.core.review.models import Field
from ema.core.review.section_transition import Status


def queue_sections(  # noqa: PLR0913
    ctx: StageContext,
    section_ids: Iterable[str],
    actor: Literal["ema", "agent"],
    fingerprint: tuple[str, ...],
    *,
    facts: dict[str, Field] | None = None,
    detail: str | None = None,
    db: sqlite3.Connection | None = None,
) -> list[str]:
    if db is None:
        with ctx.ws.connect() as connection:
            connection.execute("BEGIN")
            return queue_sections(
                ctx, section_ids, actor, fingerprint, facts=facts, detail=detail, db=connection
            )
    current_facts, materials = current_inputs(db, ctx.job)
    used_facts = current_facts if facts is None else facts
    states = {state.section_id: state for state in statuses(ctx.ws, ctx.job, db)}
    sections = {section.id: section for section in CATALOGUE}
    marked: list[str] = []
    for section_id in section_ids:
        before = states[section_id]
        # Confirmed sections require a human transition before composition replaces them.
        if before.status != Status.READY and not (before.status == Status.DRAFTED and before.stale):
            continue
        inputs = snapshot_inputs(sections[section_id], fingerprint, used_facts, materials)
        for kind in inputs[1]:
            row_id = f"{ctx.job}:{kind}"
            ctx.record_read("audit_materials", row_id, revision(db, "audit_materials", row_id) or 0)
        for key, expected in inputs[0].items():
            ctx.record_read("fields.key", f"{ctx.job}:{key}", expected or 0)
        read = ("section_states", f"{ctx.job}:{section_id}")
        ctx.record_read(*read, before.revision)

        def publish(
            connection: sqlite3.Connection,
            section_id: str = section_id,
            inputs: tuple[dict[str, int | None], dict[str, tuple[bool, str] | None]] = inputs,
            read: tuple[str, str] = read,
        ) -> None:
            after = mark_drafted(
                ctx.ws,
                ctx.job,
                section_id,
                actor,
                fingerprint,
                detail=detail,
                db=connection,
                inputs=inputs,
            )
            # Confirming a composed section changes review state, not the saved plan's inputs.
            if ctx.stage in {"audit_render", "audit_final"}:
                ctx.reads[read] = after.revision
            else:
                ctx.reads.pop(read)

        ctx.publications.append(publish)
        marked.append(section_id)
    return marked


def record_field_prefixes(
    ctx: StageContext, facts: dict[str, Field], prefixes: tuple[str, ...]
) -> None:
    for prefix in prefixes:
        members = [
            f"{key}@{field.revision}"
            for key, field in sorted(facts.items())
            if key.startswith(prefix)
        ]
        ctx.record_read("fields.prefix", f"{ctx.job}:{prefix}", collection_revision(members))
