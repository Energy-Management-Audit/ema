"""Runner ownership and recovery across CLI and API processes."""

import logging
import os
import socket
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psutil

from ema.core.jobs.events import append
from ema.core.logging import log_exception
from ema.core.workspace import Workspace

_owners: dict[Path, str] = {}
_owners_lock = threading.Lock()


def owner(ws: Workspace) -> str:
    with _owners_lock:
        if ws.root in _owners:
            return _owners[ws.root]
        owner = uuid.uuid4().hex
        with ws.connect() as db:
            db.execute(
                "INSERT INTO runners VALUES (?,?,?,?,?)",
                (
                    owner,
                    socket.gethostname(),
                    os.getpid(),
                    psutil.Process().create_time(),
                    time.time(),
                ),
            )
        _owners[ws.root] = owner
        thread = threading.Thread(target=_heartbeat, args=(ws, owner), daemon=True)
        thread.start()
        return owner


def _heartbeat(
    ws: Workspace, owner: str, stop: threading.Event | None = None, interval: float = 3.0
) -> None:
    while True:
        if stop is None:
            time.sleep(interval)
        elif stop.wait(interval):
            return
        try:
            with ws.connect() as db:
                db.execute("UPDATE runners SET heartbeat=? WHERE id=?", (time.time(), owner))
        except sqlite3.Error as exc:
            try:
                with ws.app_log() as handle:
                    log_exception(handle, exc)
            except OSError:
                logging.getLogger("ema").exception("Could not write heartbeat failure to app log")


def recover(ws: Workspace) -> None:
    host = socket.gethostname()
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            "SELECT runs.id,runs.job_id,runs.stage,runners.host,runners.pid, "
            "runners.process_start,runners.heartbeat "
            "FROM runs LEFT JOIN runners ON runs.owner=runners.id WHERE runs.state='running'"
        ).fetchall()
        for row in rows:
            fresh = row["heartbeat"] is not None and time.time() - row["heartbeat"] <= 9
            if row["host"] == host and _pid_alive(row["pid"], row["process_start"]):
                continue
            if row["host"] != host and fresh:
                continue
            db.execute(
                "UPDATE runs SET state='failed',error='interrupted',ended_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), row["id"]),
            )
            db.execute(
                "UPDATE jobs SET state=CASE WHEN type='audit' THEN 'open' "
                "ELSE 'failed' END,revision=revision+1 WHERE id=? AND state='running'",
                (row["job_id"],),
            )
            append(
                db,
                str(row["job_id"]),
                str(row["id"]),
                str(row["stage"]),
                "stage_failed",
                {"code": "interrupted"},
            )
    ws.finish_deletes()


def _pid_alive(pid: int | None, started: float | None) -> bool:
    if pid is None or started is None:
        return False
    try:
        return abs(psutil.Process(pid).create_time() - started) < 1
    except psutil.Error:
        return False
