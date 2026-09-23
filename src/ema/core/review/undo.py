"""Compensating decisions with revision-safe undo."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ema.core.errors import EmaError
from ema.core.review.models import Actor, Decision, Field
from ema.core.review.store import load_decision, load_field, mark_undone, save_decision, save_field
from ema.core.workspace import Workspace


def undo(ws: Workspace, job: str, decision_id: str, actor: Actor) -> Decision:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        original = load_decision(db, job, decision_id)
        if original.undone_by:
            raise EmaError("already_undone", "Decizia a fost deja anulată.", original.undone_by)
        current = load_field(db, job, original.field_id)
        row = db.execute(
            "SELECT seq FROM decisions WHERE id=? AND job_id=?", (decision_id, job)
        ).fetchone()
        assert row is not None  # load_decision already checked the same row in this transaction.
        later_rows = db.execute(
            "SELECT data FROM decisions WHERE job_id=? AND field_id=? AND seq>? ORDER BY seq",
            (job, original.field_id, row["seq"]),
        ).fetchall()
        later = [Decision.model_validate_json(item["data"]) for item in later_rows]
        by_id = {item.id: item for item in later}

        def active(item: Decision) -> bool:
            return item.undone_by is None or not active(by_id[item.undone_by])

        superseding = next(
            (item for item in reversed(later) if item.action != "undo" and active(item)), None
        )
        if superseding:
            raise EmaError("decision_superseded", "Decizia a fost înlocuită.", superseding.id)
        expected_revision = original.after.revision
        for item in later:
            if item.on_revision != expected_revision:
                raise EmaError(
                    "field_changed", "Câmpul a fost modificat de o etapă.", str(current.revision)
                )
            expected_revision = item.after.revision
        if current.revision != expected_revision:
            raise EmaError(
                "field_changed", "Câmpul a fost modificat de o etapă.", str(current.revision)
            )
        restored = Field.model_validate(
            {**original.before.model_dump(), "revision": current.revision + 1}
        )
        compensation = Decision(
            id=uuid.uuid4().hex,
            at=datetime.now(UTC),
            actor=actor,
            field_id=original.field_id,
            on_revision=current.revision,
            action="undo",
            before=current,
            after=restored,
        )
        save_field(db, restored)
        save_decision(db, job, compensation)
        mark_undone(db, job, original, compensation.id)
        return compensation
