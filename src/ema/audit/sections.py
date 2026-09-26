"""Audit section transitions, recorded inputs, and final-export readiness."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal

from ema.audit.applicability import applies, fact_fields
from ema.audit.catalogue import (
    CATALOGUE,
    Condition,
    MaterialKind,
    Section,
)
from ema.audit.staleness import capture_inputs, current_inputs, snapshot_inputs
from ema.core.errors import EmaError
from ema.core.review.models import Actor, Decision, Field, Issue, Readiness
from ema.core.review.section_transition import SectionState, Status, transition
from ema.core.review.store import save_decision
from ema.core.workspace import Workspace


def _section(section_id: str) -> Section:
    section = next((item for item in CATALOGUE if item.id == section_id), None)
    if section is None:
        raise EmaError("section_missing", "Secţiunea lipseşte.", section_id)
    return section


def _audit_job(ws: Workspace, job: str) -> None:
    with ws.connect() as db:
        row = db.execute("SELECT type FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone()
    if row is None or row["type"] != "audit":
        raise EmaError("audit_job_missing", "Lucrarea de audit lipseşte.", job)


def get_status(ws: Workspace, job: str, section_id: str) -> SectionState:
    _audit_job(ws, job)
    _section(section_id)
    with ws.connect() as db:
        row = db.execute(
            "SELECT data FROM section_states WHERE job_id=? AND section_id=?", (job, section_id)
        ).fetchone()
    return SectionState.parse(row["data"]) if row else SectionState(section_id)


def statuses(ws: Workspace, job: str, db: sqlite3.Connection | None = None) -> list[SectionState]:
    _audit_job(ws, job)
    if db is None:
        with ws.connect() as connection:
            return statuses(ws, job, connection)
    rows = db.execute("SELECT section_id,data FROM section_states WHERE job_id=?", (job,))
    known = {str(row["section_id"]): SectionState.parse(row["data"]) for row in rows}
    return [known.get(section.id, SectionState(section.id)) for section in CATALOGUE]


def _save(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    before: SectionState,
    after: SectionState,
    actor: Actor,
    detail: str | None = None,
    *,
    db: sqlite3.Connection | None = None,
) -> SectionState:
    if after == before:
        return before
    after = replace(after, revision=before.revision + 1)

    def write(db: sqlite3.Connection) -> None:
        row = db.execute(
            "SELECT revision FROM section_states WHERE job_id=? AND section_id=?",
            (job, before.section_id),
        ).fetchone()
        actual = int(row["revision"]) if row else 0
        if actual != before.revision:
            raise EmaError(
                "stale_revision", "Secţiunea s-a modificat între timp.", before.section_id
            )
        db.execute(
            "INSERT INTO section_states (job_id,section_id,revision,data) VALUES (?,?,?,?) "
            "ON CONFLICT(job_id,section_id) DO UPDATE SET "
            "revision=excluded.revision,data=excluded.data",
            (job, after.section_id, after.revision, json.dumps(after.payload())),
        )
        if actor == "user" or detail is not None:
            save_decision(
                db,
                job,
                Decision(
                    id=uuid.uuid4().hex,
                    at=datetime.now(UTC),
                    actor=actor,
                    field_id=after.section_id,
                    target_kind="section",
                    on_revision=before.revision,
                    action="status",
                    before=before.payload(),
                    after=after.payload(),
                    detail=detail,
                ),
            )

    if db is None:
        with ws.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            write(connection)
    else:
        write(db)
    return after


def record_material(
    ws: Workspace, job: str, kind: MaterialKind, present: bool, source: str
) -> None:
    _audit_job(ws, job)
    if not source.strip():
        raise EmaError("material_invalid", "Materialul necesită tip şi sursă.", str(kind))
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute(
            "SELECT present,source FROM audit_materials WHERE job_id=? AND kind=?",
            (job, kind.value),
        ).fetchone()
        db.execute(
            "INSERT INTO audit_materials VALUES (?,?,?,?) ON CONFLICT(job_id,kind) "
            "DO UPDATE SET present=excluded.present,source=excluded.source",
            (job, kind.value, int(present), source),
        )
        if prior is None or bool(prior["present"]) != present or prior["source"] != source:
            refresh_staleness(ws, job, db)


def _inputs(
    ws: Workspace, job: str, db: sqlite3.Connection | None = None
) -> tuple[dict[str, bool], dict[str, Field]]:
    if db is None:
        with ws.connect() as connection:
            return _inputs(ws, job, connection)
    materials = {
        str(row["kind"]): bool(row["present"])
        for row in db.execute("SELECT kind,present FROM audit_materials WHERE job_id=?", (job,))
    }
    facts = {
        str(row["key"]): Field.model_validate_json(row["data"])
        for row in db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
    }
    return materials, facts


def _computed(
    section: Section, state: SectionState, materials: dict[str, bool], facts: dict[str, Field]
) -> Status:
    if state.fingerprint:
        return Status.DRAFTED
    applicable = applies(section.applies_when, materials, facts)
    needed = [field for ref in section.facts for field in fact_fields(ref, facts)]
    return (
        Status.READY
        if applicable is True
        and (not section.facts or any(field.value is not None for field in needed))
        else Status.MISSING
    )


def set_status(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    section_id: str,
    to: Status,
    actor: Actor,
    reason: str | None = None,
    *,
    on_revision: int | None = None,
) -> SectionState:
    section = _section(section_id)
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        before = get_status(ws, job, section_id)
        if on_revision is not None and before.revision != on_revision:
            raise EmaError(
                "stale_revision",
                "Secţiunea s-a modificat între timp.",
                f"current revision: {before.revision}",
            )
        materials, facts = _inputs(ws, job, db)
        if (
            to == Status.NA_PROPOSED
            and applies(section.applies_when, materials, facts) is not False
        ):
            raise EmaError("na_trigger", "Secţiunea nu poate fi propusă n/a.", section_id)
        auto_later = (
            actor == "ema"
            and bool(section.awaits)
            and any(materials.get(kind.value) is False for kind in section.awaits)
        )
        after = transition(
            before,
            to,
            actor,
            reason,
            auto_later=auto_later,
            computed=_computed(section, before, materials, facts),
        )
        if to in (Status.NA, Status.NA_PROPOSED):
            after = replace(after, na_applicable=applies(section.applies_when, materials, facts))
        return _save(ws, job, before, after, actor, reason if actor == "ema" else None, db=db)


def recompute_ready(ws: Workspace, job: str) -> list[SectionState]:
    materials, facts = _inputs(ws, job)
    result: list[SectionState] = []
    for section, before in zip(CATALOGUE, statuses(ws, job), strict=True):
        computed = _computed(section, before, materials, facts)
        if before.status in (Status.MISSING, Status.READY):
            after = transition(before, computed, "ema")
        elif (
            before.status == Status.LATER
            and section.awaits
            and all(materials.get(kind.value) is True for kind in section.awaits)
        ):
            after = transition(before, computed, "ema", awaited_arrived=True, computed=computed)
        else:
            after = before
        result.append(_save(ws, job, before, after, "ema"))
    return result


def record_applicability(ws: Workspace, job: str, section_id: str) -> SectionState:
    """Persist the catalogue trigger or its absence for Fill review."""
    section = _section(section_id)
    before = get_status(ws, job, section_id)
    materials, facts = _inputs(ws, job)
    outcome = applies(section.applies_when, materials, facts)

    def source(item: Condition) -> str:
        if item.op == "carrier":
            return "carrier:" + ",".join(carrier.value for carrier in item.carriers)
        if item.children:
            return item.op + "(" + ",".join(source(child) for child in item.children) + ")"
        return item.op + (":" + item.key if item.key else "")

    reason = (
        "trigger: " if outcome is True else "absent: " if outcome is False else "unknown: "
    ) + source(section.applies_when)
    return _save(
        ws,
        job,
        before,
        replace(before, applicability=outcome, applicability_reason=reason),
        "ema",
        reason,
    )


def mark_drafted(
    ws: Workspace,
    job: str,
    section_id: str,
    actor: Literal["ema", "agent"],
    fingerprint: tuple[str, ...],
) -> SectionState:
    before = get_status(ws, job, section_id)
    after = transition(before, Status.DRAFTED, actor)
    fact_revisions, material_inputs = capture_inputs(ws, job, _section(section_id), fingerprint)
    all_inputs = tuple(
        dict.fromkeys(
            (
                *fingerprint,
                *(f"fact:{key}" for key in fact_revisions),
                *(f"material:{key}" for key in material_inputs),
            )
        )
    )
    return _save(
        ws,
        job,
        before,
        replace(
            after,
            fingerprint=all_inputs,
            fact_revisions=fact_revisions,
            material_inputs=material_inputs,
        ),
        actor,
    )


def mark_stale(ws: Workspace, job: str, section_id: str, changed_input: str) -> SectionState:
    before = get_status(ws, job, section_id)
    if changed_input not in before.fingerprint:
        return before
    after = transition(before, Status.DRAFTED, "ema", changed_input)
    return _save(ws, job, before, after, "ema", changed_input)


def audit_readiness(ws: Workspace, job: str, db: sqlite3.Connection | None = None) -> Readiness:
    if db is None:
        with ws.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return audit_readiness(ws, job, connection)
    refresh_staleness(ws, job, db)
    states = statuses(ws, job, db)
    materials, facts = _inputs(ws, job, db)
    issues: list[Issue] = []
    for section, state in zip(CATALOGUE, states, strict=True):
        if state.stale:
            issues.append(Issue(code="stale", message=f"Refaceţi secţiunea: {section.title}"))
        if (
            state.status == Status.NA
            and state.na_applicable is not True
            and applies(section.applies_when, materials, facts) is True
        ):
            issues.append(Issue(code="na_recheck", message=f"Reverificaţi n/a: {section.title}"))
        if state.status not in (Status.DONE, Status.NA):
            applicable = applies(section.applies_when, materials, facts)
            next_step = (
                "așteaptă preluarea dosarului"
                if applicable is None
                else (
                    "Confirmați că nu se aplică"
                    if applicable is False
                    else "Completați și confirmați secțiunea"
                )
            )
            issues.append(Issue(code="section_open", message=f"{section.title}: {next_step}"))
        for ref in section.facts:
            for field in fact_fields(ref, facts):
                if field.confidence == "conflict":
                    issues.append(
                        Issue(
                            code="conflict",
                            field_id=field.id,
                            message=f"Rezolvaţi conflictul: {section.title} / {field.label}",
                        )
                    )
    return Readiness(
        draft_ok=True,
        final_ok=not issues,
        blocking=issues,
        next=[issue.message for issue in issues],
    )


def refresh_staleness(
    ws: Workspace, job: str, db: sqlite3.Connection | None = None
) -> list[SectionState]:
    if db is None:
        with ws.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return refresh_staleness(ws, job, connection)
    facts, materials = current_inputs(db, job)
    result: list[SectionState] = []
    for section, before in zip(CATALOGUE, statuses(ws, job, db), strict=True):
        if before.status not in (Status.DRAFTED, Status.DONE) or before.stale:
            result.append(before)
            continue
        if before.fact_revisions is None or before.material_inputs is None:
            result.append(before)
            continue
        current_facts, current_materials = snapshot_inputs(
            section, before.fingerprint, facts, materials
        )
        changed = next(
            (
                f"fact:{key}"
                for key in sorted(set(before.fact_revisions) | set(current_facts))
                if before.fact_revisions.get(key) != current_facts.get(key)
            ),
            None,
        )
        if changed is None:
            changed = next(
                (
                    f"material:{key}"
                    for key in sorted(set(before.material_inputs) | set(current_materials))
                    if before.material_inputs.get(key) != current_materials.get(key)
                ),
                None,
            )
        if changed is None:
            result.append(before)
            continue
        after = transition(before, Status.DRAFTED, "ema", changed, input_changed=True)
        result.append(_save(ws, job, before, after, "ema", changed, db=db))
    return result
