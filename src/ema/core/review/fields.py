"""Field proposals, decisions and compensating undo."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from ema.core.errors import EmaError
from ema.core.review.models import Actor, Candidate, Decision, Evidence, Field, FieldSpec, Manual
from ema.core.review.store import load_field, save_decision, save_evidence, save_field
from ema.core.workspace import Workspace


def _type(value: Any) -> Literal["number", "text", "year", "date", "enum"]:
    return (
        "number"
        if isinstance(value, int | float | Decimal) and not isinstance(value, bool)
        else "text"
    )


def _candidate(value: Any, evidence: list[str]) -> Candidate:
    return Candidate(id=uuid.uuid4().hex, value=value, evidence=evidence)


def _changed(field: Field, **updates: Any) -> Field:
    return Field.model_validate({**field.model_dump(), **updates, "revision": field.revision + 1})


def _correction_value(field: Field, value: Any) -> Any:
    if isinstance(value, bool):
        raise EmaError("value_invalid", "Valoarea este invalidă.", field.id)
    if field.value_type == "number":
        try:
            result = Decimal(str(value))
            if not result.is_finite():
                raise InvalidOperation
            return result
        except (InvalidOperation, ValueError) as exc:
            raise EmaError("value_invalid", "Valoarea este invalidă.", field.id) from exc
    if field.value_type == "year":
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return int(value)
        raise EmaError("value_invalid", "Valoarea este invalidă.", field.id)
    if not isinstance(value, str):
        raise EmaError("value_invalid", "Valoarea este invalidă.", field.id)
    return value


def propose(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    key: str | FieldSpec,
    value: Any,
    evidence: list[Evidence],
    *,
    state: Literal["supplied", "extracted", "enriched", "calculated", "manual"],
    derivation: Any = None,
) -> Field:
    spec = (
        key
        if isinstance(key, FieldSpec)
        else FieldSpec(key=key, label=key, value_type=_type(value))
    )
    if value is None:
        raise EmaError("value_missing", "Valoarea propusă lipsește.", spec.key)
    if state == "manual" and not evidence:
        raise EmaError("evidence_missing", "Valoarea introdusă necesită dovadă.", spec.key)
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        save_evidence(db, job, evidence)
        refs = [item.id for item in evidence]
        row = db.execute(
            "SELECT id FROM fields WHERE job_id=? AND key=?", (job, spec.key)
        ).fetchone()
        if row is None:
            field = Field(
                id=uuid.uuid4().hex,
                job_id=job,
                key=spec.key,
                chapter=spec.chapter,
                label=spec.label,
                value_type=spec.value_type,
                unit=spec.unit,
                required=spec.required,
                value=value,
                state=state,
                presence="found",
                confidence="exact" if refs else "partial",
                evidence=refs,
                derivation=derivation,
            )
        else:
            old = load_field(db, job, row["id"])
            if old.value == value:
                return old
            candidates = (
                old.alternatives or [_candidate(old.value, old.evidence)]
                if old.value is not None
                else []
            )
            if not any(item.value == value for item in candidates):
                candidates.append(_candidate(value, refs))
            protected = (
                old.review == "corrected"
                or old.state == "manual"
                or (old.state in {"supplied", "extracted"} and state == "enriched")
            )
            if protected:
                field = _changed(
                    old,
                    alternatives=candidates,
                    chosen=None,
                    confidence="conflict" if len(candidates) >= 2 else old.confidence,
                )
            else:
                field = _changed(
                    old,
                    value=value,
                    state=state,
                    presence="found",
                    evidence=refs,
                    derivation=derivation,
                    review="pending",
                    alternatives=candidates,
                    chosen=None,
                    confidence="conflict" if len(candidates) >= 2 else "partial",
                    failure=None,
                )
        save_field(db, field)
        return field


def mark_absent(
    ws: Workspace,
    job: str,
    key: str | FieldSpec,
    presence: Literal["not_found", "failed"],
    failure: str | None = None,
    evidence: list[Evidence] | None = None,
) -> Field:
    spec = key if isinstance(key, FieldSpec) else FieldSpec(key=key, label=key, value_type="text")
    if presence == "failed" and not failure:
        raise EmaError("failure_missing", "Cauza erorii lipsește.", spec.key)
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        save_evidence(db, job, evidence or [])
        evidence_ids = [item.id for item in evidence or []]
        row = db.execute(
            "SELECT id FROM fields WHERE job_id=? AND key=?", (job, spec.key)
        ).fetchone()
        if row:
            old = load_field(db, job, row["id"])
            if old.state == "manual" or (evidence_ids and old.value is not None):
                return old
            field = _changed(
                old,
                value=None,
                presence=presence,
                failure=failure,
                review="pending",
                confidence="none",
                alternatives=[],
                chosen=None,
                evidence=evidence_ids or old.evidence,
            )
        else:
            field = Field(
                id=uuid.uuid4().hex,
                job_id=job,
                key=spec.key,
                chapter=spec.chapter,
                label=spec.label,
                value_type=spec.value_type,
                required=spec.required,
                unit=spec.unit,
                state="extracted",
                presence=presence,
                failure=failure,
                evidence=evidence_ids,
            )
        save_field(db, field)
        return field


def fields(ws: Workspace, job: str, *, status: str | None = None) -> list[Field]:
    with ws.connect() as db:
        rows = db.execute("SELECT data FROM fields WHERE job_id=? ORDER BY key", (job,)).fetchall()
    result = [Field.model_validate_json(row["data"]) for row in rows]
    if status == "conflict":
        return [field for field in result if field.confidence == "conflict"]
    if status == "missing":
        return [field for field in result if field.value is None or field.review == "rejected"]
    if status == "uncertain":
        return [field for field in result if field.confidence in ("partial", "conflict", "none")]
    if status in ("pending", "accepted", "corrected", "rejected"):
        return [field for field in result if field.review == status]
    return result


def _apply(
    field: Field,
    action: Literal["accept", "correct", "reject", "choose"],
    value: Any,
    alternative: str | None,
    actor: Actor,
) -> tuple[Field, list[Evidence]]:
    if action == "accept":
        if field.value is None or field.confidence == "conflict":
            raise EmaError("field_unresolved", "Câmpul nu poate fi acceptat.", field.id)
        return _changed(field, review="accepted"), []
    if action == "reject":
        return _changed(field, review="rejected"), []
    if action == "correct":
        if value is None:
            raise EmaError("value_missing", "Valoarea corectată lipsește.", field.id)
        value = _correction_value(field, value)
        evidence = Evidence(
            id=uuid.uuid4().hex,
            provenance="manual",
            locator=Manual(who=actor),
            method="manual",
            retrieved_at=datetime.now(UTC),
            highlight="none",
        )
        candidates = field.alternatives or (
            [_candidate(field.value, field.evidence)] if field.value is not None else []
        )
        chosen = _candidate(value, [evidence.id])
        candidates = [*candidates, chosen]
        return _changed(
            field,
            value=value,
            state="manual",
            presence="found",
            review="corrected",
            evidence=[evidence.id],
            alternatives=candidates,
            chosen=chosen.id,
            confidence="exact",
            failure=None,
        ), [evidence]
    candidate = next((item for item in field.alternatives if item.id == alternative), None)
    if candidate is None:
        raise EmaError("alternative_missing", "Alternativa nu există.", str(alternative))
    return _changed(
        field,
        value=candidate.value,
        evidence=candidate.evidence,
        chosen=candidate.id,
        confidence="exact",
        review="accepted",
    ), []


def _decide(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    field_id: str,
    action: Literal["accept", "correct", "reject", "choose"],
    on_revision: int,
    actor: Actor,
    *,
    value: Any,
    alternative: str | None,
    batch_id: str | None,
) -> Decision:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        return _decide_in_tx(
            db,
            job,
            field_id,
            action,
            on_revision,
            actor,
            value=value,
            alternative=alternative,
            batch_id=batch_id,
        )


def _decide_in_tx(  # noqa: PLR0913
    db: sqlite3.Connection,
    job: str,
    field_id: str,
    action: Literal["accept", "correct", "reject", "choose"],
    on_revision: int,
    actor: Actor,
    *,
    value: Any,
    alternative: str | None,
    batch_id: str | None,
) -> Decision:
    before = load_field(db, job, field_id)
    if before.revision != on_revision:
        raise EmaError("stale_revision", "Câmpul a fost modificat între timp.", field_id)
    after, evidence = _apply(before, action, value, alternative, actor)
    save_evidence(db, job, evidence)
    decision = Decision(
        id=uuid.uuid4().hex,
        at=datetime.now(UTC),
        actor=actor,
        field_id=field_id,
        on_revision=on_revision,
        action=action,
        before=before,
        after=after,
        batch_id=batch_id,
    )
    save_field(db, after)
    save_decision(db, job, decision)
    return decision


def decide(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    field_id: str,
    action: Literal["accept", "correct", "reject", "choose"],
    on_revision: int,
    actor: Actor,
    *,
    value: Any = None,
    alternative: str | None = None,
) -> Decision:
    return _decide(
        ws,
        job,
        field_id,
        action,
        on_revision,
        actor,
        value=value,
        alternative=alternative,
        batch_id=None,
    )


def decide_in_connection(
    db: sqlite3.Connection,
    job: str,
    field_id: str,
    on_revision: int,
    actor: Actor,
) -> Decision:
    """Accept a field inside a workflow transaction with related persistence."""
    return _decide_in_tx(
        db,
        job,
        field_id,
        "accept",
        on_revision,
        actor,
        value=None,
        alternative=None,
        batch_id=None,
    )


def accept_batch(
    ws: Workspace, job: str, field_ids_with_revisions: list[tuple[str, int]], actor: Actor
) -> list[Decision]:
    batch_id = uuid.uuid4().hex
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        return [
            _decide_in_tx(
                db,
                job,
                field_id,
                "accept",
                revision,
                actor,
                value=None,
                alternative=None,
                batch_id=batch_id,
            )
            for field_id, revision in field_ids_with_revisions
        ]


def log(ws: Workspace, job: str) -> list[Decision]:
    with ws.connect() as db:
        rows = db.execute(
            "SELECT data FROM decisions WHERE job_id=? ORDER BY seq", (job,)
        ).fetchall()
    return [Decision.model_validate_json(row["data"]) for row in rows]


def conflicts(ws: Workspace, job: str) -> list[Field]:
    return fields(ws, job, status="conflict")
