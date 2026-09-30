"""SQLite job lifecycle and the in-process thread runner."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ema import __version__
from ema.core.errors import EmaError
from ema.core.jobs.activity import activity
from ema.core.jobs.events import ProgressEvent, append, subscribe
from ema.core.jobs.failure import record_failure
from ema.core.jobs.fingerprint import collection_revision
from ema.core.jobs.reads import (
    JobStatus,
    get_job,
    latest_ready_run,
    list_jobs,
    revision,
    status,
)
from ema.core.jobs.runner import owner, recover
from ema.core.logging import write_event
from ema.core.workspace import SlotVersion, Workspace

__all__ = [
    "JobStatus",
    "activity",
    "cancel",
    "create_job",
    "get_job",
    "latest_ready_run",
    "list_jobs",
    "recover",
    "run_stage",
    "status",
    "subscribe",
]

JobType = Literal["invoices", "piee", "audit", "reporting"]
JobState = Literal["created", "running", "ready", "failed", "cancelled", "open"]
JobId = str
RunId = str


@dataclass(frozen=True)
class StageOutcome:
    item_failures: list[str] = field(default_factory=list[str])
    warnings: list[str] = field(default_factory=list[str])


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
    with ws.connect() as db:
        registered = db.execute("SELECT 1 FROM clients WHERE id=?", (client_slug,)).fetchone()
        if type != "reporting" and registered is None:
            raise EmaError("client_unknown", "Clientul nu există.", client_slug)
        ws.make_job_folders(relative)
        db.execute(
            "INSERT INTO jobs (id,type,client_slug,year,relative_path,state,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (job, type, client_slug, year, relative, "created", _now()),
        )
    return job


class StageContext:
    def __init__(self, ws: Workspace, job: JobId, run_id: RunId, stage: str) -> None:
        self.ws, self.job, self.run_id, self.stage = ws, job, run_id, stage
        self.reads: dict[tuple[str, str], int] = {}
        self.inputs: dict[str, str] = {}
        self.changed_reads = False
        self.outputs: list[tuple[Path, str]] = []
        self.publications: list[Callable[[sqlite3.Connection], None]] = []

    def read_slot(self, slot: str, record: bool = True) -> SlotVersion:
        with self.ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT s.revision,v.* FROM slots s JOIN slot_versions v ON v.job_id=s.job_id "
                "AND v.slot=s.name AND v.version=s.active_version WHERE s.job_id=? AND s.name=?",
                (self.job, slot),
            ).fetchone()
            if row is None:
                raise EmaError("slot_missing", "Fişierul cerut lipseşte.", slot)
            client = db.execute("SELECT client_slug FROM jobs WHERE id=?", (self.job,)).fetchone()[
                0
            ]
            db.execute(
                "INSERT OR IGNORE INTO run_inputs VALUES (?,?,?)",
                (self.run_id, client, row["file_sha"]),
            )
        if record:
            self.record_read("slots", f"{self.job}:{slot}", int(row["revision"]))
        self.inputs[f"slot:{slot}"] = str(row["file_sha"])
        return SlotVersion(
            self.job,
            slot,
            int(row["version"]),
            str(row["file_sha"]),
            str(row["origin"]),
            row["converted_from"],
            row["original_name"],
        )

    def read_slots(self, prefix: str, record: bool = True) -> list[SlotVersion]:
        names = self.ws.list_slots(self.job, prefix)
        self.record_read("slots.collection", f"{self.job}:{prefix}", collection_revision(names))
        return [self.read_slot(slot, record=record) for slot in names]

    def record_read(self, table: str, row_id: str, revision: int) -> None:
        key = (table, row_id)
        if key in self.reads and self.reads[key] != revision:
            self.changed_reads = True
        self.reads.setdefault(key, revision)

    def read_review_row(self, table: Literal["fields", "decisions"], row_id: str) -> str:
        if table not in ("fields", "decisions"):
            raise EmaError("read_table", "Tipul datelor citite este invalid.", table)
        with self.ws.connect() as db:
            row = db.execute(
                f'SELECT revision,data FROM "{table}" WHERE id=? AND job_id=?',
                (row_id, self.job),
            ).fetchone()
        if row is None:
            raise EmaError("review_row_missing", "Datele de revizuire lipsesc.", row_id)
        self.record_read(table, row_id, int(row["revision"]))
        return str(row["data"])

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

    def save_output(self, source: Path, name: str, *, kind: str = "draft") -> Path:
        if kind not in ("draft", "final"):
            raise EmaError("output_kind", "Tipul documentului este invalid.", kind)
        with self.ws.connect() as db:
            output = self.ws.save_output(db, self.job, self.run_id, source, name)
        self.outputs.append((output, kind))
        return output

    def progress(self, done: int, total: int, message: str) -> None:
        event = ProgressEvent(self.run_id, done, total, message)
        with self.ws.connect() as db:
            append(
                db,
                self.job,
                self.run_id,
                self.stage,
                "stage_progress",
                {"done": done, "total": total, "message": message},
            )
        with self.ws.connect() as db, self.ws.job_log(db, self.job) as handle:
            write_event(handle, "progress", **asdict(event))

    def cancelled(self) -> bool:
        with self.ws.connect() as db:
            row = db.execute(
                "SELECT cancel_requested FROM runs WHERE id=?", (self.run_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])


def _finish(  # noqa: C901, PLR0912
    ws: Workspace,
    context: StageContext,
    outcome: StageOutcome | None,
    error: str | None,
    on_finish: Callable[[sqlite3.Connection, str], None] | None = None,
    failure: EmaError | None = None,
) -> None:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT state,cancel_requested FROM runs WHERE id=?", (context.run_id,)
        ).fetchone()
        if row is None or row["state"] != "running":
            return
        stale = context.changed_reads or any(
            revision(db, table, row_id) != expected_revision
            for (table, row_id), expected_revision in context.reads.items()
        )
        cancelled = bool(row["cancel_requested"])
        state = "cancelled" if cancelled else "failed" if error else "ready"
        publication = "stale" if stale else "current" if state == "ready" else None
        if publication == "current":
            for publish in context.publications:
                publish(db)
        fingerprint_data = {
            "reads": sorted(
                (table, row_id, revision) for (table, row_id), revision in context.reads.items()
            ),
            "inputs": context.inputs,
            "ema": __version__,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_data, sort_keys=True).encode()
        ).hexdigest()
        if state != "ready":
            for path, _kind in context.outputs:
                path.unlink(missing_ok=True)
        directory = ws.artifact_dir(db, context.job, context.stage, context.run_id)
        ws.record_artifacts(db, context.run_id, directory)
        if state == "ready":
            ws.record_outputs(db, context.job, context.run_id, context.outputs)
        for (table, row_id), read_revision in context.reads.items():
            db.execute(
                "INSERT INTO run_reads VALUES (?,?,?,?)",
                (context.run_id, table, row_id, read_revision),
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
        if on_finish is not None:
            on_finish(db, state)
        if outcome:
            for item_id in outcome.item_failures:
                opaque_id = hashlib.sha256(item_id.encode()).hexdigest()[:16]
                append(
                    db,
                    context.job,
                    context.run_id,
                    context.stage,
                    "item_failed",
                    {"item_id": opaque_id, "code": "item_failed"},
                )
        if state == "ready":
            event_type = "stage_finished"
            payload = {
                "state": "ready",
                "publication": publication,
                "item_failures": len(outcome.item_failures) if outcome else 0,
                "warnings": len(outcome.warnings) if outcome else 0,
            }
        elif state == "cancelled":
            event_type, payload = "stage_cancelled", {"state": "cancelled"}
        elif failure is not None:
            # A known refusal keeps its code and message so a screen can say what went wrong.
            event_type = "stage_failed"
            payload = {"code": failure.code, "message": failure.user_message_ro}
        else:
            event_type, payload = "stage_failed", {"code": "stage_failed"}
        append(db, context.job, context.run_id, context.stage, event_type, payload)


def run_stage(
    ws: Workspace,
    job: JobId,
    stage: str,
    fn: Callable[[StageContext], StageOutcome],
    *,
    on_finish: Callable[[sqlite3.Connection, str], None] | None = None,
    on_revision: int | None = None,
) -> RunId:
    runner_owner = owner(ws)
    run = uuid.uuid4().hex
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT state,revision FROM jobs WHERE id=? AND deleted=0", (job,)
        ).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        if on_revision is not None and row["revision"] != on_revision:
            raise EmaError("stale_revision", "Lucrarea s-a modificat.", "")
        if row["state"] == "running":
            raise EmaError("job_running", "Lucrarea rulează deja.", job)
        ws.artifact_dir(db, job, stage, run)
        db.execute(
            "INSERT INTO runs (id,job_id,stage,owner,state,started_at) VALUES (?,?,?,?,?,?)",
            (run, job, stage, runner_owner, "running", _now()),
        )
        db.execute("UPDATE jobs SET state='running',revision=revision+1 WHERE id=?", (job,))
        append(db, job, run, stage, "stage_started", {"state": "running"})
    context = StageContext(ws, job, run, stage)
    threading.Thread(
        target=_execute_stage,
        args=(context, fn, on_finish),
        daemon=True,
        name=f"ema-{stage}-{run[:8]}",
    ).start()
    return run


def _execute_stage(
    context: StageContext,
    fn: Callable[[StageContext], StageOutcome],
    on_finish: Callable[[sqlite3.Connection, str], None] | None = None,
) -> None:
    ws, job, run = context.ws, context.job, context.run_id
    outcome: StageOutcome | None = None
    error: str | None = None
    failure: EmaError | None = None
    fatal: BaseException | None = None
    try:
        outcome = fn(context)
    except BaseException as exc:
        error = str(exc) or type(exc).__name__
        failure = exc if isinstance(exc, EmaError) else None
        if not isinstance(exc, Exception):
            fatal = exc
        record_failure(ws, job, exc)
    finally:
        try:
            _finish(ws, context, outcome, error, on_finish, failure)
        except Exception as exc:
            record_failure(ws, job, exc)
            with ws.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT state FROM runs WHERE id=?", (run,)).fetchone()
                if current is not None and current["state"] == "running":
                    db.execute(
                        "UPDATE runs SET state='failed',error=?,ended_at=? WHERE id=?",
                        (str(exc), _now(), run),
                    )
                    db.execute(
                        "UPDATE jobs SET state=CASE WHEN type='audit' THEN 'open' "
                        "ELSE 'failed' END,revision=revision+1 WHERE id=?",
                        (job,),
                    )
                    append(db, job, run, context.stage, "stage_failed", {"code": "stage_failed"})
        finally:
            with ws.connect() as db:
                row = db.execute("SELECT state FROM runs WHERE id=?", (run,)).fetchone()
            if row is None or row["state"] != "ready":
                for path, _kind in context.outputs:
                    path.unlink(missing_ok=True)
    if fatal is not None:
        raise fatal


def cancel(ws: Workspace, job: JobId) -> None:
    with ws.connect() as db:
        db.execute("UPDATE runs SET cancel_requested=1 WHERE job_id=? AND state='running'", (job,))
