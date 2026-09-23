"""SQLite job lifecycle and the in-process thread runner."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import threading
import traceback
import uuid
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ema import __version__
from ema.core.errors import EmaError
from ema.core.jobs.runner import owner, recover
from ema.core.logging import log_exception, write_event
from ema.core.workspace import SlotVersion, Workspace

__all__ = ["cancel", "create_job", "list_jobs", "recover", "run_stage", "status", "subscribe"]

JobType = Literal["invoices", "piee", "audit", "reporting"]
JobState = Literal["created", "running", "ready", "failed", "cancelled", "open"]
JobId = str
RunId = str


@dataclass(frozen=True)
class ProgressEvent:
    run_id: str
    done: int
    total: int
    message: str


@dataclass(frozen=True)
class StageOutcome:
    item_failures: list[str] = field(default_factory=list[str])
    warnings: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class JobStatus:
    id: str
    type: str
    state: str
    runs: list[dict[str, Any]]


_events: dict[str, list[ProgressEvent]] = {}
_events_condition = threading.Condition()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_job(ws: Workspace, type: JobType, client_slug: str, year: int | None) -> JobId:
    if type not in ("invoices", "piee", "audit", "reporting"):
        raise EmaError("job_type", "Tipul lucrării este invalid.", str(type))
    if not client_slug or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for c in client_slug
    ):
        raise EmaError("invalid_client", "Identificatorul clientului este invalid.", client_slug)
    job = uuid.uuid4().hex
    relative = f"clients/{client_slug}/jobs/{year or 'none'}-{type}-{job[:8]}"
    ws.make_job_folders(relative)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO jobs (id,type,client_slug,year,relative_path,state,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (job, type, client_slug, year, relative, "created", _now()),
        )
    return job


def list_jobs(ws: Workspace) -> list[dict[str, Any]]:
    with ws.connect() as db:
        rows = db.execute(
            "SELECT id,type,client_slug,year,state FROM jobs WHERE deleted=0 ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def status(ws: Workspace, job: JobId) -> JobStatus:
    with ws.connect() as db:
        row = db.execute(
            "SELECT id,type,state FROM jobs WHERE id=? AND deleted=0", (job,)
        ).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        runs = db.execute(
            "SELECT id,stage,state,publication,fingerprint,outcome,error "
            "FROM runs WHERE job_id=? ORDER BY started_at",
            (job,),
        ).fetchall()
    return JobStatus(str(row["id"]), str(row["type"]), str(row["state"]), [dict(r) for r in runs])


class StageContext:
    def __init__(self, ws: Workspace, job: JobId, run_id: RunId, stage: str) -> None:
        self.ws, self.job, self.run_id, self.stage = ws, job, run_id, stage
        self.reads: dict[tuple[str, str], int] = {}
        self.inputs: dict[str, str] = {}
        self.changed_reads = False
        self.outputs: list[Path] = []

    def read_slot(self, slot: str) -> SlotVersion:
        with self.ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT s.revision,v.* FROM slots s JOIN slot_versions v ON v.job_id=s.job_id "
                "AND v.slot=s.name AND v.version=s.active_version WHERE s.job_id=? AND s.name=?",
                (self.job, slot),
            ).fetchone()
            if row is None:
                raise EmaError("slot_missing", "Fișierul cerut lipsește.", slot)
            client = db.execute("SELECT client_slug FROM jobs WHERE id=?", (self.job,)).fetchone()[
                0
            ]
            db.execute(
                "INSERT OR IGNORE INTO run_inputs VALUES (?,?,?)",
                (self.run_id, client, row["file_sha"]),
            )
        self.record_read("slots", f"{self.job}:{slot}", int(row["revision"]))
        self.inputs[f"slot:{slot}"] = str(row["file_sha"])
        return SlotVersion(
            self.job,
            slot,
            int(row["version"]),
            str(row["file_sha"]),
            str(row["origin"]),
            row["converted_from"],
        )

    def record_read(self, table: str, row_id: str, revision: int) -> None:
        key = (table, row_id)
        if key in self.reads and self.reads[key] != revision:
            self.changed_reads = True
        self.reads.setdefault(key, revision)

    def read_setting(self, key: str) -> Any:
        with self.ws.connect() as db:
            row = db.execute(
                "SELECT settings,settings_revision FROM jobs WHERE id=? AND deleted=0", (self.job,)
            ).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", self.job)
        self.record_read("jobs.settings", self.job, int(row["settings_revision"]))
        return json.loads(str(row["settings"])).get(key)

    def record_input(
        self,
        *,
        template: str | None = None,
        factors: str | None = None,
        prompt: str | None = None,
        model: str | None = None,
    ) -> None:
        for key, value in (
            ("template", template),
            ("factors", factors),
            ("prompt", prompt),
            ("model", model),
        ):
            if value is not None:
                self.inputs[key] = value

    def artifact_dir(self) -> Path:
        with self.ws.connect() as db:
            return self.ws.artifact_dir(db, self.job, self.stage, self.run_id)

    def save_output(self, source: Path, name: str) -> Path:
        with self.ws.connect() as db:
            output = self.ws.save_output(db, self.job, self.run_id, source, name)
        self.outputs.append(output)
        return output

    def progress(self, done: int, total: int, message: str) -> None:
        event = ProgressEvent(self.run_id, done, total, message)
        with _events_condition:
            _events.setdefault(self.job, []).append(event)
            _events_condition.notify_all()
        with self.ws.connect() as db, self.ws.job_log(db, self.job) as handle:
            write_event(handle, "progress", **asdict(event))

    def cancelled(self) -> bool:
        with self.ws.connect() as db:
            row = db.execute(
                "SELECT cancel_requested FROM runs WHERE id=?", (self.run_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])


def _revision(db: sqlite3.Connection, table: str, row_id: str) -> int | None:
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


def _finish(
    ws: Workspace, context: StageContext, outcome: StageOutcome | None, error: str | None
) -> None:
    fingerprint_data = {
        "reads": sorted(
            (table, row_id, revision) for (table, row_id), revision in context.reads.items()
        ),
        "inputs": context.inputs,
        "ema": __version__,
    }
    fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT state,cancel_requested FROM runs WHERE id=?", (context.run_id,)
        ).fetchone()
        if row is None or row["state"] != "running":
            return
        stale = context.changed_reads or any(
            _revision(db, table, row_id) != revision
            for (table, row_id), revision in context.reads.items()
        )
        cancelled = bool(row["cancel_requested"])
        state = "cancelled" if cancelled else "failed" if error else "ready"
        publication = "stale" if stale else "current" if state == "ready" else None
        directory = context.artifact_dir()
        ws.record_artifacts(db, context.run_id, directory)
        if state == "ready":
            ws.record_outputs(db, context.job, context.run_id, context.outputs)
        for (table, row_id), revision in context.reads.items():
            db.execute(
                "INSERT INTO run_reads VALUES (?,?,?,?)", (context.run_id, table, row_id, revision)
            )
        db.execute(
            "UPDATE runs SET state=?,publication=?,fingerprint=?,outcome=?,error=?,ended_at=? "
            "WHERE id=?",
            (
                state,
                publication,
                fingerprint,
                json.dumps(asdict(outcome)) if outcome else None,
                error,
                _now(),
                context.run_id,
            ),
        )
        job_state = (
            "open"
            if db.execute("SELECT type FROM jobs WHERE id=?", (context.job,)).fetchone()[0]
            == "audit"
            else state
        )
        db.execute(
            "UPDATE jobs SET state=?,revision=revision+1 WHERE id=?", (job_state, context.job)
        )


def run_stage(
    ws: Workspace, job: JobId, stage: str, fn: Callable[[StageContext], StageOutcome]
) -> RunId:
    runner_owner = owner(ws)
    run = uuid.uuid4().hex
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT state FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        if row["state"] == "running":
            raise EmaError("job_running", "Lucrarea rulează deja.", job)
        ws.artifact_dir(db, job, stage, run)
        db.execute(
            "INSERT INTO runs (id,job_id,stage,owner,state,started_at) VALUES (?,?,?,?,?,?)",
            (run, job, stage, runner_owner, "running", _now()),
        )
        db.execute("UPDATE jobs SET state='running',revision=revision+1 WHERE id=?", (job,))
    context = StageContext(ws, job, run, stage)
    threading.Thread(
        target=_execute_stage, args=(context, fn), daemon=True, name=f"ema-{stage}-{run[:8]}"
    ).start()
    return run


def _record_failure(ws: Workspace, job: JobId, exc: BaseException) -> None:
    try:
        with ws.connect() as db, ws.job_log(db, job) as handle:
            log_exception(handle, exc)
    except BaseException as log_error:
        try:
            with ws.app_log() as handle:
                log_exception(handle, exc)
                log_exception(handle, log_error)
        except BaseException as app_log_error:
            try:
                traceback.print_exception(exc, file=sys.stderr)
                traceback.print_exception(log_error, file=sys.stderr)
                traceback.print_exception(app_log_error, file=sys.stderr)
            except BaseException:
                return  # Diagnostics cannot interrupt the run state transition.


def _execute_stage(context: StageContext, fn: Callable[[StageContext], StageOutcome]) -> None:
    ws, job, run = context.ws, context.job, context.run_id
    outcome: StageOutcome | None = None
    error: str | None = None
    fatal: BaseException | None = None
    try:
        outcome = fn(context)
    except BaseException as exc:
        error = str(exc) or type(exc).__name__
        if not isinstance(exc, Exception):
            fatal = exc
        _record_failure(ws, job, exc)
    finally:
        try:
            _finish(ws, context, outcome, error)
        except Exception as exc:
            _record_failure(ws, job, exc)
            with ws.connect() as db:
                db.execute(
                    "UPDATE runs SET state='failed',error=?,ended_at=? "
                    "WHERE id=? AND state='running'",
                    (str(exc), _now(), run),
                )
                db.execute(
                    "UPDATE jobs SET state=CASE WHEN type='audit' THEN 'open' "
                    "ELSE 'failed' END,revision=revision+1 WHERE id=?",
                    (job,),
                )
        finally:
            with ws.connect() as db:
                row = db.execute("SELECT state FROM runs WHERE id=?", (run,)).fetchone()
            if row is None or row["state"] != "ready":
                for path in context.outputs:
                    path.unlink(missing_ok=True)
    if fatal is not None:
        raise fatal


def cancel(ws: Workspace, job: JobId) -> None:
    with ws.connect() as db:
        db.execute("UPDATE runs SET cancel_requested=1 WHERE job_id=? AND state='running'", (job,))


def subscribe(ws: Workspace, job: JobId) -> Iterator[ProgressEvent]:
    index = 0
    while True:
        with _events_condition:
            events = _events.get(job, [])
            if index < len(events):
                event = events[index]
                index += 1
            else:
                if status(ws, job).state != "running":
                    return
                _events_condition.wait(timeout=1)
                continue
        yield event
