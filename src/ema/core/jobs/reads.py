"""Resolve stage read-set revisions at publish and export."""

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from ema.core.errors import EmaError
from ema.core.jobs.fingerprint import collection_revision
from ema.core.workspace import Workspace


@dataclass(frozen=True)
class JobStatus:
    id: str
    type: str
    state: str
    revision: int
    runs: list[dict[str, Any]]


def status(ws: Workspace, job: str) -> JobStatus:
    with ws.connect() as db:
        row = db.execute(
            "SELECT id,type,state,revision FROM jobs WHERE id=? AND deleted=0", (job,)
        ).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        runs = db.execute(
            "SELECT id,stage,state,publication,fingerprint,outcome,error "
            "FROM runs WHERE job_id=? ORDER BY started_at",
            (job,),
        ).fetchall()
    return JobStatus(
        str(row["id"]),
        str(row["type"]),
        str(row["state"]),
        int(row["revision"]),
        [dict(r) for r in runs],
    )


def get_job(ws: Workspace, job: str) -> dict[str, object]:
    with ws.connect() as db:
        row = db.execute(
            "SELECT id,type,client_slug,year,state,revision FROM jobs WHERE id=? AND deleted=0",
            (job,),
        ).fetchone()
    if row is None:
        raise EmaError("job_missing", "Lucrarea nu există.", job)
    return dict(row)


def latest_ready_run(ws: Workspace, job: str, stage: str) -> str | None:
    with ws.connect() as db:
        row = db.execute(
            "SELECT id FROM runs WHERE job_id=? AND stage=? AND state='ready' "
            "AND publication='current' ORDER BY ended_at DESC LIMIT 1",
            (job, stage),
        ).fetchone()
    return str(row["id"]) if row else None


def revision(db: sqlite3.Connection, table: str, row_id: str) -> int | None:
    if table == "slots":
        job, slot = row_id.split(":", 1)
        row = db.execute(
            "SELECT revision FROM slots WHERE job_id=? AND name=?", (job, slot)
        ).fetchone()
    elif table == "slots.collection":
        job, prefix = row_id.split(":", 1)
        collection = f"{prefix}/" if prefix else ""
        rows = db.execute(
            "SELECT name FROM slots WHERE job_id=? AND substr(name,1,?)=? "
            "AND active_version IS NOT NULL ORDER BY name",
            (job, len(collection), collection),
        ).fetchall()
        return collection_revision([str(row["name"]) for row in rows])
    elif table == "jobs.settings":
        row = db.execute(
            "SELECT settings_revision AS revision FROM jobs WHERE id=? AND deleted=0", (row_id,)
        ).fetchone()
    else:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", table):
            raise EmaError("read_table", "Tipul datelor citite este invalid.", table)
        columns = {entry["name"] for entry in db.execute(f'PRAGMA table_info("{table}")')}
        if not {"id", "revision"} <= columns:
            raise EmaError("read_table", "Tipul datelor citite este invalid.", table)
        row = db.execute(f'SELECT revision FROM "{table}" WHERE id=?', (row_id,)).fetchone()
    return int(row["revision"]) if row else None


def run_current(db: sqlite3.Connection, run_id: str) -> bool:
    run = db.execute("SELECT state,publication FROM runs WHERE id=?", (run_id,)).fetchone()
    if run is None or run["state"] != "ready" or run["publication"] != "current":
        return False
    reads = db.execute(
        "SELECT table_name,row_id,revision FROM run_reads WHERE run_id=?", (run_id,)
    ).fetchall()
    return all(revision(db, row["table_name"], row["row_id"]) == row["revision"] for row in reads)
