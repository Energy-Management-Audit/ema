"""Resolve stage read-set revisions at publish and export."""

import re
import sqlite3

from ema.core.errors import EmaError


def revision(db: sqlite3.Connection, table: str, row_id: str) -> int | None:
    if table == "slots":
        job, slot = row_id.split(":", 1)
        row = db.execute(
            "SELECT revision FROM slots WHERE job_id=? AND name=?", (job, slot)
        ).fetchone()
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
    reads = db.execute(
        "SELECT table_name,row_id,revision FROM run_reads WHERE run_id=?", (run_id,)
    ).fetchall()
    return all(revision(db, row["table_name"], row["row_id"]) == row["revision"] for row in reads)
