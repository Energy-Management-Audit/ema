"""SQLite persistence for review records."""

from __future__ import annotations

import sqlite3

from ema.core.errors import EmaError
from ema.core.review.models import Decision, Evidence, Field


def load_field(db: sqlite3.Connection, job: str, field_id: str) -> Field:
    row = db.execute("SELECT data FROM fields WHERE id=? AND job_id=?", (field_id, job)).fetchone()
    if row is None:
        raise EmaError("field_missing", "Câmpul nu există.", field_id)
    return Field.model_validate_json(row["data"])


def save_field(db: sqlite3.Connection, field: Field) -> None:
    db.execute(
        "INSERT INTO fields (id,job_id,key,revision,data) VALUES (?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,data=excluded.data",
        (field.id, field.job_id, field.key, field.revision, field.model_dump_json()),
    )


def save_evidence(db: sqlite3.Connection, job: str, evidence: list[Evidence]) -> None:
    for item in evidence:
        existing = db.execute("SELECT job_id,data FROM evidence WHERE id=?", (item.id,)).fetchone()
        payload = item.model_dump_json(exclude={"file_name"})
        if existing and (existing["data"] != payload or existing["job_id"] != job):
            raise EmaError("evidence_immutable", "Dovada nu poate fi modificată.", item.id)
        if not existing:
            db.execute("INSERT INTO evidence VALUES (?,?,?)", (item.id, job, payload))


def load_decision(db: sqlite3.Connection, job: str, decision_id: str) -> Decision:
    row = db.execute(
        "SELECT data FROM decisions WHERE id=? AND job_id=?", (decision_id, job)
    ).fetchone()
    if row is None:
        raise EmaError("decision_missing", "Decizia nu există.", decision_id)
    return Decision.model_validate_json(row["data"])


def save_decision(db: sqlite3.Connection, job: str, decision: Decision) -> None:
    db.execute(
        "INSERT INTO decisions (id,job_id,field_id,at,data,seq) "
        "VALUES (?,?,?,?,?,(SELECT COALESCE(MAX(seq),0)+1 FROM decisions))",
        (decision.id, job, decision.field_id, decision.at.isoformat(), decision.model_dump_json()),
    )


def mark_undone(db: sqlite3.Connection, job: str, decision: Decision, undo_id: str) -> None:
    changed = decision.model_copy(update={"undone_by": undo_id})
    db.execute(
        "UPDATE decisions SET data=?,revision=revision+1 WHERE id=? AND job_id=?",
        (changed.model_dump_json(), decision.id, job),
    )
