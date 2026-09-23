"""Shared readiness issues and approval-bound exports."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

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
                    message=f"Lipsește: {spec.label}",
                )
            )
    return Readiness(
        draft_ok=True, final_ok=not issues, blocking=issues, next=[item.message for item in issues]
    )


def readiness_hash(ws: Workspace, job: str, readiness: Readiness, workflow: Workflow) -> str:
    with ws.connect() as db:
        snapshot = _field_revisions(db, job)
    return _hash(readiness, snapshot, workflow.readiness_snapshot(ws, job))


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


def _latest_decision(db: sqlite3.Connection, job: str) -> str | None:
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


def output_path(ws: Workspace, job: str, output_id: str) -> Path:
    with ws.connect() as db:
        row = db.execute(
            "SELECT relative_path FROM outputs WHERE id=? AND job_id=?", (output_id, job)
        ).fetchone()
    if row is None:
        raise EmaError("output_missing", "Documentul lipsește.", output_id)
    return ws.path(str(row["relative_path"]))


def approve_final(
    ws: Workspace, job: str, output_id: str, readiness_hash: str, actor: Actor
) -> Approval:
    if actor != "user":
        raise EmaError("approval_requires_user", "Aprobarea aparține utilizatorului.", job)
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if _latest_output(db, job) != output_id:
            raise EmaError("output_stale", "Documentul nu este versiunea curentă.", output_id)
        row = db.execute("SELECT kind FROM outputs WHERE id=?", (output_id,)).fetchone()
        if row is None or row["kind"] != "final":
            raise EmaError("output_not_final", "Documentul nu este final.", output_id)
        approval = Approval(
            id=uuid.uuid4().hex,
            job_id=job,
            output_id=output_id,
            readiness_hash=readiness_hash,
            on_decision=_latest_decision(db, job),
            at=datetime.now(UTC),
            actor=actor,
        )
        db.execute(
            "INSERT INTO approvals VALUES (?,?,?,?,?,?,?)",
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


def _require_ready(readiness: Readiness, final: bool, job: str) -> None:
    if final and not readiness.final_ok:
        raise EmaError("not_ready", "Lucrarea nu este pregătită pentru export.", job)
    if not final and not readiness.draft_ok:
        raise EmaError("not_ready", "Ciorna nu poate fi exportată.", job)


def export(
    ws: Workspace,
    job: str,
    workflow: Workflow,
    *,
    final: bool,
    dest: Path,
    actor: Actor,
) -> Path:
    draft_output_id: str | None = None
    if not final:
        readiness = workflow.readiness(ws, job)
        _require_ready(readiness, False, job)
        draft_output_id = workflow.render(ws, job, "draft")
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        output_id = _latest_output(db, job) if final else draft_output_id
        if output_id is None:
            raise EmaError("output_missing", "Documentul lipsește.", job)
        row = db.execute(
            "SELECT relative_path,sha,run_id,kind FROM outputs WHERE id=?", (output_id,)
        ).fetchone()
        if row is None:
            raise EmaError("output_missing", "Documentul lipsește.", output_id)
        if row["kind"] != ("final" if final else "draft"):
            code, message = (
                ("output_not_final", "Documentul nu este final.")
                if final
                else ("output_not_draft", "Documentul nu este o ciornă.")
            )
            raise EmaError(code, message, output_id)
        if final:
            readiness = workflow.readiness(ws, job)
            _require_ready(readiness, True, job)
            digest = _hash(
                readiness, _field_revisions(db, job), workflow.readiness_snapshot(ws, job)
            )
            approval_row = db.execute(
                "SELECT 1 FROM approvals WHERE job_id=? AND output_id=? "
                "AND readiness_hash=? AND on_decision IS ? LIMIT 1",
                (job, output_id, digest, _latest_decision(db, job)),
            ).fetchone()
            if approval_row is None:
                raise EmaError("approval_required", "Aprobarea finală lipsește.", output_id)
        if not run_current(db, str(row["run_id"])):
            raise EmaError("output_stale", "Documentul nu mai este actual.", output_id)
        return copy_output(ws, str(row["relative_path"]), str(row["sha"]), dest)
