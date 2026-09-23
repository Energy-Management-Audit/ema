"""Current-read checks shared by stage publication and output export."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from ema.core.errors import EmaError


def collection_revision(names: list[str]) -> int:
    digest = hashlib.sha256(json.dumps(names).encode()).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def revision(db: sqlite3.Connection, table: str, row_id: str) -> int | None:
    if table == "slots":
        job, slot = row_id.split(":", 1)
        row = db.execute(
            "SELECT revision FROM slots WHERE job_id=? AND name=?", (job, slot)
        ).fetchone()
    elif table == "slots.collection":
        job, prefix = row_id.split(":", 1)
        collection = f"{prefix}/"
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


def run_current(db: sqlite3.Connection, run: str) -> bool:
    rows = db.execute(
        "SELECT table_name,row_id,revision FROM run_reads WHERE run_id=?", (run,)
    ).fetchall()
    return bool(rows) and all(
        revision(db, str(row["table_name"]), str(row["row_id"])) == int(row["revision"])
        for row in rows
    )
