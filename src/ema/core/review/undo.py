"""Compensating decisions with revision-safe undo."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from ema.core.errors import EmaError
from ema.core.review.models import Actor, Decision, Field
from ema.core.review.section_transition import SectionState, Status, transition
from ema.core.review.store import load_decision, load_field, mark_undone, save_decision, save_field
from ema.core.workspace import Workspace


def undo(ws: Workspace, job: str, decision_id: str, actor: Actor) -> Decision:  # noqa: C901
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        original = load_decision(db, job, decision_id)
        if original.undone_by:
            raise EmaError("already_undone", "Decizia a fost deja anulată.", original.undone_by)
        if original.target_kind == "field":
            current: Field | dict[str, Any] = load_field(db, job, original.field_id)
        else:
            section_row = db.execute(
                "SELECT data FROM section_states WHERE job_id=? AND section_id=?",
                (job, original.field_id),
            ).fetchone()
            if section_row is None:
                raise EmaError("section_missing", "Secțiunea lipsește.", original.field_id)
            current = json.loads(section_row["data"])
        row = db.execute(
            "SELECT seq FROM decisions WHERE id=? AND job_id=?", (decision_id, job)
        ).fetchone()
        assert row is not None  # load_decision already checked the same row in this transaction.
        later_rows = db.execute(
            "SELECT data FROM decisions WHERE job_id=? AND field_id=? AND seq>? ORDER BY seq",
            (job, original.field_id, row["seq"]),
        ).fetchall()
        later = [
            decision
            for item in later_rows
            if (decision := Decision.model_validate_json(item["data"])).target_kind
            == original.target_kind
        ]
        by_id = {item.id: item for item in later}

        def active(item: Decision) -> bool:
            return item.undone_by is None or not active(by_id[item.undone_by])

        superseding = next(
            (item for item in reversed(later) if item.action != "undo" and active(item)), None
        )
        if superseding:
            raise EmaError("decision_superseded", "Decizia a fost înlocuită.", superseding.id)
        expected_revision = _revision(original.after)
        for item in later:
            if item.on_revision != expected_revision:
                raise EmaError(
                    "field_changed", "Câmpul a fost modificat de o etapă.", str(_revision(current))
                )
            expected_revision = _revision(item.after)
        if _revision(current) != expected_revision:
            raise EmaError(
                "field_changed", "Câmpul a fost modificat de o etapă.", str(_revision(current))
            )
        if original.target_kind == "field":
            assert isinstance(original.before, Field)
            restored: Field | dict[str, Any] = Field.model_validate(
                {**original.before.model_dump(), "revision": _revision(current) + 1}
            )
        else:
            assert isinstance(original.before, dict)
            assert isinstance(original.after, dict)
            assert isinstance(current, dict)
            restored_state = _validate_section_undo(db, job, current, original, actor)
            restored = {**restored_state.payload(), "revision": _revision(current) + 1}
        compensation = Decision(
            id=uuid.uuid4().hex,
            at=datetime.now(UTC),
            actor=actor,
            field_id=original.field_id,
            target_kind=original.target_kind,
            on_revision=_revision(current),
            action="undo",
            before=current,
            after=restored,
        )
        if isinstance(restored, Field):
            save_field(db, restored)
        else:
            db.execute(
                "UPDATE section_states SET revision=?,data=? WHERE job_id=? AND section_id=?",
                (restored["revision"], json.dumps(restored), job, original.field_id),
            )
        save_decision(db, job, compensation)
        mark_undone(db, job, original, compensation.id)
        return compensation


def _revision(value: Field | dict[str, Any]) -> int:
    return value.revision if isinstance(value, Field) else int(value["revision"])


def _validate_section_undo(
    db: sqlite3.Connection, job: str, current: dict[str, Any], original: Decision, actor: Actor
) -> SectionState:
    assert isinstance(original.before, dict)
    assert isinstance(original.after, dict)
    current_section = SectionState.parse(current)
    previous_section = SectionState.parse(original.before)
    decided_section = SectionState.parse(original.after)
    if actor != "user" and decided_section.status in (Status.DONE, Status.NA):
        raise EmaError(
            "transition_forbidden",
            "Tranziția secțiunii este interzisă.",
            f"undo {decided_section.status.value} by {actor}",
        )
    changed_input = _changed_section_input(db, job, previous_section)
    previous_state = transition(
        current_section,
        previous_section.status,
        actor,
        changed_input or previous_section.reason,
        computed=previous_section.status,
        compensation=actor == "user" and decided_section.status == Status.DONE,
        input_changed=actor == "user" and changed_input is not None,
    )
    return previous_state


def _changed_section_input(db: sqlite3.Connection, job: str, previous: SectionState) -> str | None:
    """Compare the restored draft's captured inputs with the live rows in this transaction."""
    # The caller has an open transaction; snapshots are persisted on the section state.
    # An absent snapshot is legacy/unknown, so it cannot prove a change.
    fact_revisions = previous.fact_revisions
    material_inputs = previous.material_inputs
    if fact_revisions is not None:
        for key, revision in fact_revisions.items():
            row = db.execute(
                "SELECT data FROM fields WHERE job_id=? AND key=?", (job, key)
            ).fetchone()
            current_revision = None
            if row is not None:
                current_revision = int(json.loads(row["data"])["revision"])
            if current_revision != revision:
                return f"fact:{key}"
    if material_inputs is not None:
        for key, material in material_inputs.items():
            row = db.execute(
                "SELECT present,source FROM audit_materials WHERE job_id=? AND kind=?", (job, key)
            ).fetchone()
            current_material = (bool(row["present"]), str(row["source"])) if row else None
            if current_material != material:
                return f"material:{key}"
    return None
