"""Shared readiness issues and approval-bound exports."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from ema.core.errors import EmaError
from ema.core.jobs.reads import run_current
from ema.core.review.fields import fields
from ema.core.review.models import Actor, Approval, FieldSpec, Issue, Readiness
from ema.core.workspace import Workspace
from ema.core.workspace.export import copy_output


class Workflow(Protocol):
    """A workflow snapshots every non-field input used by readiness."""

    def readiness(self, ws: Workspace, job: str) -> Readiness: ...

    def readiness_snapshot(self, ws: Workspace, job: str) -> dict[str, object]: ...

    def render(self, ws: Workspace, job: str, kind: str) -> str: ...


def base_readiness(ws: Workspace, job: str, catalogue: list[FieldSpec]) -> Readiness:
    by_key = {field.key: field for field in fields(ws, job)}
    issues: list[Issue] = []
    for field in by_key.values():
        if field.confidence == "conflict":
            issues.append(
                Issue(code="conflict", field_id=field.id, message=f"Conflict: {field.label}")
            )
    for spec in catalogue:
        field = by_key.get(spec.key)
        if spec.required and (field is None or field.value is None or field.review == "rejected"):
            issues.append(
                Issue(
                    code="missing",
                    field_id=field.id if field else None,
                    message=f"Lipseşte: {spec.label}",
                )
            )
    return Readiness(
        draft_ok=True, final_ok=not issues, blocking=issues, next=[item.message for item in issues]
    )


def readiness_hash(ws: Workspace, job: str, readiness: Readiness, workflow: Workflow) -> str:
    with ws.connect() as db:
        snapshot = _field_revisions(db, job)
    return _hash(readiness, snapshot, workflow.readiness_snapshot(ws, job))


def readiness_hash_in_tx(
    ws: Workspace,
    db: sqlite3.Connection,
    job: str,
    readiness: Readiness,
    workflow: Workflow,
) -> str:
    snapshot_reader = getattr(workflow, "readiness_snapshot_in_tx", None)
    snapshot = snapshot_reader(db, job) if snapshot_reader else workflow.readiness_snapshot(ws, job)
    return _hash(readiness, _field_revisions(db, job), snapshot)


def _field_revisions(db: sqlite3.Connection, job: str) -> list[tuple[str, int]]:
    return [
        (str(row["id"]), int(row["revision"]))
        for row in db.execute("SELECT id,revision FROM fields WHERE job_id=? ORDER BY id", (job,))
    ]


def _hash(
    readiness: Readiness, snapshot: list[tuple[str, int]], workflow_snapshot: dict[str, object]
) -> str:
    payload = {
        "readiness": readiness.model_dump(mode="json"),
        "fields": snapshot,
        "workflow": workflow_snapshot,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def latest_decision(db: sqlite3.Connection, job: str) -> str | None:
    row = db.execute(
        "SELECT id FROM decisions WHERE job_id=? ORDER BY seq DESC LIMIT 1", (job,)
    ).fetchone()
    return str(row["id"]) if row else None


def _latest_output(db: sqlite3.Connection, job: str) -> str | None:
    row = db.execute(
        "SELECT id FROM outputs WHERE job_id=? ORDER BY seq DESC LIMIT 1",
        (job,),
    ).fetchone()
    return str(row["id"]) if row else None


class FinalOutput(BaseModel):
    output_id: str
    created_at: str
    files: list[str]


def final_view(db: sqlite3.Connection, job: str, output_id: str | None) -> FinalOutput | None:
    row = db.execute(
        "SELECT o.id,o.run_id,r.ended_at FROM outputs o JOIN runs r ON r.id=o.run_id "
        "WHERE o.job_id=? AND o.id=? AND o.kind='final'",
        (job, output_id),
    ).fetchone()
    if row is None:
        return None
    files = [
        Path(str(item[0])).name.removeprefix(f"{row['run_id']}-")
        for item in db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND run_id=? ORDER BY seq",
            (job, row["run_id"]),
        )
    ]
    return FinalOutput(output_id=str(row["id"]), created_at=str(row["ended_at"]), files=files)


def current_final(
    db: sqlite3.Connection, job: str, workflow: Workflow | None = None
) -> FinalOutput | None:
    selector = getattr(workflow, "current_final", None)
    return selector(db, job) if selector else final_view(db, job, _latest_output(db, job))


def final_checks(ws: Workspace, job: str, workflow: Workflow) -> dict[str, object]:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        reader = getattr(workflow, "readiness_in_tx", None)
        readiness = reader(ws, job, db) if reader else workflow.readiness(ws, job)
        final = current_final(db, job, workflow)
        return {
            "final": final.model_dump(mode="json") if final else None,
            "readiness": readiness.model_dump(mode="json"),
            "readiness_hash": readiness_hash_in_tx(ws, db, job, readiness, workflow),
        }


def output_path(ws: Workspace, job: str, output_id: str) -> Path:
    with ws.connect() as db:
        row = db.execute(
            "SELECT relative_path FROM outputs WHERE id=? AND job_id=?", (output_id, job)
        ).fetchone()
    if row is None:
        raise EmaError("output_missing", "Documentul lipseşte.", output_id)
    return ws.path(str(row["relative_path"]))


def approve_final(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    output_id: str,
    readiness_hash: str,
    actor: Actor,
    *,
    db: sqlite3.Connection | None = None,
    workflow: Workflow | None = None,
) -> Approval:
    if actor != "user":
        raise EmaError("approval_requires_user", "Aprobarea aparţine utilizatorului.", job)
    if db is None:
        with ws.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return approve_final(
                ws, job, output_id, readiness_hash, actor, db=connection, workflow=workflow
            )
    selected = current_final(db, job, workflow)
    if selected is None or selected.output_id != output_id:
        raise EmaError("output_stale", "Documentul nu este versiunea curentă.", output_id)
    row = db.execute("SELECT kind FROM outputs WHERE id=?", (output_id,)).fetchone()
    if row is None or row["kind"] != "final":
        raise EmaError("output_not_final", "Documentul nu este final.", output_id)
    approval = Approval(
        id=uuid.uuid4().hex,
        job_id=job,
        output_id=output_id,
        readiness_hash=readiness_hash,
        on_decision=latest_decision(db, job),
        at=datetime.now(UTC),
        actor=actor,
    )
    db.execute(
        "INSERT INTO approvals(id,job_id,output_id,readiness_hash,on_decision,at,actor) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            approval.id,
            job,
            output_id,
            readiness_hash,
            approval.on_decision,
            approval.at.isoformat(),
            actor,
        ),
    )
    return approval


def approvals(ws: Workspace, job: str) -> list[Approval]:
    """Every final approval of the job, newest first."""
    with ws.connect() as db:
        db.execute("BEGIN")
        if db.execute("SELECT 1 FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone() is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        rows = db.execute(
            "SELECT id,job_id,output_id,readiness_hash,on_decision,at,actor,exported_at "
            "FROM approvals "
            "WHERE job_id=? ORDER BY at DESC",
            (job,),
        ).fetchall()
    return [Approval.model_validate(dict(row)) for row in rows]


def _require_ready(readiness: Readiness, final: bool, job: str) -> None:
    if final and not readiness.final_ok:
        raise EmaError("not_ready", "Lucrarea nu este pregătită pentru export.", job)
    if not final and not readiness.draft_ok:
        raise EmaError("not_ready", "Ciorna nu poate fi exportată.", job)


def export(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    workflow: Workflow,
    *,
    final: bool,
    dest: Path,
    actor: Actor,
    expected_output_id: str | None = None,
) -> Path:
    draft_output_id: str | None = None
    if not final:
        readiness = workflow.readiness(ws, job)
        _require_ready(readiness, False, job)
        draft_output_id = workflow.render(ws, job, "draft")
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        selected = current_final(db, job, workflow) if final else None
        output_id = selected.output_id if selected else draft_output_id
        if output_id is None:
            raise EmaError("output_missing", "Documentul lipseşte.", job)
        if expected_output_id is not None and output_id != expected_output_id:
            raise EmaError("output_stale", "Documentul nu este versiunea curentă.", job)
        row = db.execute(
            "SELECT relative_path,sha,run_id,kind FROM outputs WHERE id=?", (output_id,)
        ).fetchone()
        if row is None:
            raise EmaError("output_missing", "Documentul lipseşte.", output_id)
        if row["kind"] != ("final" if final else "draft"):
            code, message = (
                ("output_not_final", "Documentul nu este final.")
                if final
                else ("output_not_draft", "Documentul nu este o ciornă.")
            )
            raise EmaError(code, message, output_id)
        if final:
            in_tx = getattr(workflow, "readiness_in_tx", None)
            readiness = in_tx(ws, job, db) if in_tx is not None else workflow.readiness(ws, job)
            if not readiness.final_ok:
                db.commit()  # Persist audit staleness before refusing the export.
            _require_ready(readiness, True, job)
            snapshot_in_tx = getattr(workflow, "readiness_snapshot_in_tx", None)
            workflow_snapshot = (
                snapshot_in_tx(db, job)
                if snapshot_in_tx is not None
                else workflow.readiness_snapshot(ws, job)
            )
            digest = _hash(readiness, _field_revisions(db, job), workflow_snapshot)
            approval_row = db.execute(
                "SELECT 1 FROM approvals WHERE job_id=? AND output_id=? "
                "AND readiness_hash=? AND on_decision IS ? LIMIT 1",
                (job, output_id, digest, latest_decision(db, job)),
            ).fetchone()
            if approval_row is None:
                raise EmaError("approval_required", "Aprobarea finală lipseşte.", output_id)
        if not run_current(db, str(row["run_id"])):
            raise EmaError("output_stale", "Documentul nu mai este actual.", output_id)
        return copy_output(ws, str(row["relative_path"]), str(row["sha"]), dest)
