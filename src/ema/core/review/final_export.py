"""Approve and deliver a complete immutable final run."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from ema.core.errors import EmaError
from ema.core.jobs.events import append
from ema.core.jobs.reads import run_current
from ema.core.review.readiness import (
    Workflow,
    approve_final,
    current_final,
    latest_decision,
    readiness_hash_in_tx,
)
from ema.core.workspace import Workspace
from ema.core.workspace.export import copy_output


class ExportFile(BaseModel):
    name: str
    path: str


class ExportResult(BaseModel):
    approved_at: str
    files: list[ExportFile]
    folder: str


def default_export_folder(ws: Workspace, job: str) -> Path:
    with ws.connect() as db:
        row = db.execute(
            "SELECT j.type,j.year,c.name FROM jobs j LEFT JOIN clients c ON c.id=j.client_slug "
            "WHERE j.id=? AND j.deleted=0",
            (job,),
        ).fetchone()
    if row is None:
        raise EmaError("job_missing", "Lucrarea nu există.", job)
    title = {"audit": "Audit energetic", "piee": "PIEE", "invoices": "Facturi"}[row["type"]]
    name = f"{row['name'] or job} {title} {row['year'] or ''}".strip()
    safe = "".join("_" if char in '/\\<>:"|?*' or ord(char) < 32 else char for char in name)
    return ws.root / "exports" / safe.rstrip(". ")


def _approval(db: sqlite3.Connection, job: str, output_id: str, digest: str) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM approvals WHERE job_id=? AND output_id=? AND readiness_hash=? "
        "AND on_decision IS ? ORDER BY at DESC LIMIT 1",
        (job, output_id, digest, latest_decision(db, job)),
    ).fetchone()


def _validated_final_run(
    ws: Workspace,
    job: str,
    output_id: str,
    readiness_hash: str,
    *,
    db: sqlite3.Connection,
    workflow: Workflow,
) -> str:
    record = db.execute("SELECT state FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone()
    if record is None:
        raise EmaError("job_missing", "Lucrarea nu există.", job)
    if record["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", job)
    selected = current_final(db, job, workflow)
    if selected is None or selected.output_id != output_id:
        raise EmaError("output_stale", "Documentul nu este versiunea curentă.", output_id)
    in_tx = getattr(workflow, "readiness_in_tx", None)
    readiness = in_tx(ws, job, db) if in_tx else workflow.readiness(ws, job)
    if not readiness.final_ok:
        db.commit()  # Preserve discovered staleness even when delivery is refused.
        raise EmaError("not_ready", "Lucrarea nu este pregătită pentru export.", job)
    digest = readiness_hash_in_tx(ws, db, job, readiness, workflow)
    if digest != readiness_hash:
        raise EmaError("hash_mismatch", "Datele de pregătire nu corespund.", job)
    output = db.execute(
        "SELECT run_id,kind FROM outputs WHERE job_id=? AND id=?",
        (job, output_id),
    ).fetchone()
    if output is None or output["kind"] != "final":
        raise EmaError("output_not_final", "Documentul nu este final.", output_id)
    run = str(output["run_id"])
    if not run_current(db, run):
        raise EmaError("output_stale", "Documentul nu mai este actual.", output_id)
    return run


def export_final(
    ws: Workspace,
    job: str,
    output_id: str,
    readiness_hash: str,
    dest_dir: Path,
    *,
    workflow: Workflow,
) -> ExportResult:
    try:
        folder = dest_dir.expanduser().resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        raise EmaError(
            "output_path", "Directorul pentru export este invalid.", str(dest_dir)
        ) from exc
    if folder.is_file():
        raise EmaError("output_path", "Directorul pentru export este invalid.", str(folder))
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        run = _validated_final_run(ws, job, output_id, readiness_hash, db=db, workflow=workflow)
        rows = db.execute(
            "SELECT relative_path,sha FROM outputs WHERE job_id=? AND run_id=? ORDER BY seq",
            (job, run),
        ).fetchall()
        for row in rows:
            source = ws.path(str(row["relative_path"]))
            if folder.is_relative_to(source.parent) or source.is_relative_to(folder):
                raise EmaError(
                    "output_path", "Exportul trebuie salvat separat de documente.", str(folder)
                )
        approved = _approval(db, job, output_id, readiness_hash)
        if approved is None:
            approval = approve_final(
                ws, job, output_id, readiness_hash, "user", db=db, workflow=workflow
            )
            approved_at, approval_id = approval.at.isoformat(), approval.id
        else:
            approved_at, approval_id = str(approved["at"]), str(approved["id"])
        files: list[ExportFile] = []
        try:
            for row in rows:
                relative = str(row["relative_path"])
                name = Path(relative).name.removeprefix(f"{run}-")
                copied = copy_output(ws, relative, str(row["sha"]), folder / name)
                files.append(ExportFile(name=name, path=str(copied)))
        except (OSError, EmaError) as exc:
            # Approval survives a failed delivery; its null timestamp distinguishes a retry.
            db.commit()
            if isinstance(exc, EmaError):
                raise
            raise EmaError(
                "output_copy_failed", "Copierea documentelor a eşuat. Reluaţi exportul.", str(exc)
            ) from exc
        db.execute(
            "UPDATE approvals SET exported_at=COALESCE(exported_at,?) WHERE id=?",
            (datetime.now(UTC).isoformat(), approval_id),
        )
        result = ExportResult(approved_at=approved_at, files=files, folder=str(folder))
        previous = db.execute(
            "SELECT 1 FROM job_events WHERE job_id=? AND type='exported' AND payload=? LIMIT 1",
            (job, json.dumps(result.model_dump(mode="json"))),
        ).fetchone()
        if previous is None:
            append(db, job, run, None, "exported", result.model_dump(mode="json"))
        return result
