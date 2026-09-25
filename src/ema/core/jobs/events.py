"""Durable, ordered job progress used by HTTP replay and the CLI."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ema.core.workspace import Workspace


@dataclass(frozen=True)
class JobEvent:
    seq: int
    job_id: str
    run_id: str | None
    stage: str | None
    type: str
    at: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ProgressEvent:
    run_id: str
    done: int
    total: int
    message: str


def append(
    db: sqlite3.Connection,
    job_id: str,
    run_id: str | None,
    stage: str | None,
    type: str,
    payload: dict[str, Any],
) -> int:
    cursor = db.execute(
        "INSERT INTO job_events(job_id,run_id,stage,type,at,payload) VALUES (?,?,?,?,?,?)",
        (job_id, run_id, stage, type, datetime.now(UTC).isoformat(), json.dumps(payload)),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def replay(ws: Workspace, job_id: str, cursor: int) -> tuple[list[JobEvent], bool]:
    """Read events and terminal state from one SQLite snapshot."""
    with ws.connect() as db:
        db.execute("BEGIN")
        rows = db.execute(
            "SELECT * FROM job_events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 100",
            (job_id, cursor),
        ).fetchall()
        running = db.execute(
            "SELECT 1 FROM runs WHERE job_id=? AND state='running' LIMIT 1", (job_id,)
        ).fetchone()
        job = db.execute("SELECT state FROM jobs WHERE id=? AND deleted=0", (job_id,)).fetchone()
        latest = db.execute(
            "SELECT state FROM runs WHERE job_id=? ORDER BY started_at DESC LIMIT 1", (job_id,)
        ).fetchone()
    return [
        JobEvent(
            int(row["seq"]),
            str(row["job_id"]),
            row["run_id"],
            row["stage"],
            str(row["type"]),
            str(row["at"]),
            json.loads(str(row["payload"])),
        )
        for row in rows
    ], bool(job and not running and latest and latest["state"] in ("ready", "failed", "cancelled"))


def subscribe(ws: Workspace, job: str) -> Iterator[ProgressEvent]:
    cursor = 0
    while True:
        events, terminal = replay(ws, job, cursor)
        for event in events:
            cursor = event.seq
            if event.type == "stage_progress":
                yield ProgressEvent(
                    event.run_id or "",
                    int(event.payload["done"]),
                    int(event.payload["total"]),
                    str(event.payload["message"]),
                )
        if not events and terminal:
            return
        time.sleep(1)
