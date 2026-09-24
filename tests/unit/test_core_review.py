"""Regressions found in the first review of S1."""

import os
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import zipfile
from contextlib import nullcontext
from pathlib import Path

import psutil
import pytest

from ema.core.backup import backup
from ema.core.jobs import StageOutcome, cancel, create_job, recover, run_stage, runner, status
from ema.core.workspace import Workspace
from ema.core.workspace import schema as workspace_schema


def wait_run(ws: Workspace, job: str) -> dict[str, object]:
    for _ in range(200):
        result = status(ws, job)
        if result.state != "running":
            return result.runs[-1]
        time.sleep(0.01)
    pytest.fail("stage did not finish")


def test_recover_keeps_live_pid_even_with_expired_heartbeat(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "client", 2025)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO runners VALUES (?,?,?,?,?)",
            ("live", socket.gethostname(), os.getpid(), psutil.Process().create_time(), 0),
        )
        db.execute(
            "INSERT INTO runs (id,job_id,stage,owner,state,started_at) "
            "VALUES ('run',?,'extract','live','running','now')",
            (job,),
        )
        db.execute("UPDATE jobs SET state='running' WHERE id=?", (job,))
    recover(ws)
    assert status(ws, job).state == "running"
    assert status(ws, job).runs[0]["state"] == "running"


def test_heartbeat_retries_after_sqlite_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    with ws.connect() as db:
        db.execute("INSERT INTO runners VALUES ('runner','host',1,0,0)")
    original_connect = ws.connect
    retried = threading.Event()
    calls = 0

    def flaky_connect():  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("synthetic lock timeout")
        retried.set()
        return original_connect()

    monkeypatch.setattr(ws, "connect", flaky_connect)
    stop = threading.Event()
    worker = threading.Thread(target=runner._heartbeat, args=(ws, "runner", stop, 0.01))
    worker.start()
    assert retried.wait(2)
    stop.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    with original_connect() as db:
        assert db.execute("SELECT heartbeat FROM runners WHERE id='runner'").fetchone()[0] > 0
    assert "synthetic lock timeout" in (ws.root / "logs" / "ema.jsonl").read_text()


def test_audit_run_failure_and_recovery_leave_job_open(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "client", 2025)

    def broken(ctx):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic stage failure")

    run_stage(ws, job, "extract", broken)
    assert wait_run(ws, job)["state"] == "failed"
    assert status(ws, job).state == "open"
    with ws.connect() as db:
        db.execute(
            "INSERT INTO runs (id,job_id,stage,owner,state,started_at) "
            "VALUES ('interrupted',?,'review','dead','running','now')",
            (job,),
        )
        db.execute("UPDATE jobs SET state='running' WHERE id=?", (job,))
    recover(ws)
    assert status(ws, job).state == "open"
    assert status(ws, job).runs[-1]["error"] == "interrupted"


def test_audit_publish_fallback_leaves_job_open(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "client", 2025)

    def invalid(ctx):  # type: ignore[no-untyped-def]
        return object()

    run_stage(ws, job, "extract", invalid)
    assert wait_run(ws, job)["state"] == "failed"
    assert status(ws, job).state == "open"


def test_cancel_from_second_workspace_is_seen_by_stage(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "client", 2025)
    started = threading.Event()
    proceed = threading.Event()

    def stage(ctx):  # type: ignore[no-untyped-def]
        started.set()
        assert proceed.wait(2)
        assert ctx.cancelled()
        return StageOutcome()

    run_stage(ws, job, "extract", stage)
    assert started.wait(2)
    cancel(Workspace(ws.root), job)
    proceed.set()
    assert wait_run(ws, job)["state"] == "cancelled"
    assert status(ws, job).state == "open"


def test_interrupted_delete_keeps_row_on_rmtree_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "client", 2025)
    with ws.connect() as db:
        folder = ws.job_path(db, job)
        db.execute("UPDATE jobs SET deleted=1 WHERE id=?", (job,))
    original_rmtree = shutil.rmtree

    def blocked(path):  # type: ignore[no-untyped-def]
        raise PermissionError("synthetic delete denial")

    monkeypatch.setattr(shutil, "rmtree", blocked)
    ws.finish_deletes()
    with ws.connect() as db:
        assert db.execute("SELECT deleted FROM jobs WHERE id=?", (job,)).fetchone()[0] == 1
    assert folder.exists()
    assert "synthetic delete denial" in (ws.root / "logs" / "ema.jsonl").read_text()
    monkeypatch.setattr(shutil, "rmtree", original_rmtree)
    Workspace(ws.root)
    with ws.connect() as db:
        assert db.execute("SELECT 1 FROM jobs WHERE id=?", (job,)).fetchone() is None
    assert not folder.exists()


def test_repeated_slot_read_across_edit_is_stale(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "client", 2025)
    first, second = tmp_path / "first", tmp_path / "second"
    first.write_text("first")
    second.write_text("second")
    ws.set_slot(job, "input", ws.add_file("client", first))
    read = threading.Event()
    resume = threading.Event()

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.read_slot("input")
        read.set()
        assert resume.wait(2)
        ctx.read_slot("input")
        return StageOutcome()

    run_stage(ws, job, "extract", stage)
    assert read.wait(2)
    ws.set_slot(job, "input", ws.add_file("client", second))
    resume.set()
    assert wait_run(ws, job)["publication"] == "stale"


def test_failed_run_discards_unpublished_output(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "client", 2025)
    saved: list[Path] = []

    def stage(ctx):  # type: ignore[no-untyped-def]
        source = ctx.artifact_dir() / "source.txt"
        source.write_text("output")
        saved.append(ctx.save_output(source, "result.txt"))
        raise RuntimeError("after output")

    run_stage(ws, job, "extract", stage)
    assert wait_run(ws, job)["state"] == "failed"
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM outputs WHERE job_id=?", (job,)).fetchone()[0] == 0
    assert saved and not saved[0].exists()
    saved[0].write_text("orphan after interrupted cleanup")
    ws.gc()
    assert not saved[0].exists()


def test_system_exit_and_failed_log_write_finish_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "client", 2025)
    failures: list[BaseException] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: failures.append(args.exc_value))

    class BrokenLog:
        def write(self, value: str) -> int:
            raise OSError("log write failed")

    monkeypatch.setattr(ws, "job_log", lambda db, job: nullcontext(BrokenLog()))

    def stage(ctx):  # type: ignore[no-untyped-def]
        raise SystemExit("stage exited")

    run_stage(ws, job, "extract", stage)
    result = wait_run(ws, job)
    assert result["state"] == "failed"
    assert result["error"] == "stage exited"
    assert len(failures) == 1 and isinstance(failures[0], SystemExit)


@pytest.mark.parametrize("failure", ["stage", "publish"])
@pytest.mark.parametrize("app_log_denied", [False, True])
def test_failed_job_log_preserves_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    app_log_denied: bool,
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "client", 2025)

    def denied_job_log(db, job):  # type: ignore[no-untyped-def]
        raise PermissionError("job log denied")

    monkeypatch.setattr(ws, "job_log", denied_job_log)
    if app_log_denied:

        def denied_app_log():  # type: ignore[no-untyped-def]
            raise PermissionError("app log denied")

        monkeypatch.setattr(ws, "app_log", denied_app_log)

    def stage(ctx):  # type: ignore[no-untyped-def]
        if failure == "stage":
            raise RuntimeError("stage failed")
        return object()

    run_stage(ws, job, "extract", stage)
    assert wait_run(ws, job)["state"] == "failed"
    assert status(ws, job).state == "failed"
    diagnostics = (
        capsys.readouterr().err if app_log_denied else (ws.root / "logs" / "ema.jsonl").read_text()
    )
    assert "Traceback" in diagnostics
    assert ("stage failed" if failure == "stage" else "TypeError") in diagnostics
    assert "job log denied" in diagnostics
    if app_log_denied:
        assert "app log denied" in diagnostics


def test_each_deleted_job_commits_before_next_folder_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    first = create_job(ws, "invoices", "client", 2025)
    second = create_job(ws, "invoices", "client", 2026)
    with ws.connect() as db:
        db.execute("UPDATE jobs SET deleted=1 WHERE id IN (?,?)", (first, second))
    original = shutil.rmtree
    calls = 0

    def remove(path):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 2:
            with ws.connect() as db:
                assert db.execute("SELECT 1 FROM jobs WHERE id=?", (first,)).fetchone() is None
            raise PermissionError("second folder blocked")
        original(path)

    monkeypatch.setattr(shutil, "rmtree", remove)
    ws.finish_deletes()
    with ws.connect() as db:
        assert db.execute("SELECT 1 FROM jobs WHERE id=?", (second,)).fetchone() is not None


def test_interrupted_backup_has_no_complete_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    original = zipfile.ZipFile.write

    def interrupted(self, filename, arcname=None, compress_type=None, compresslevel=None):  # type: ignore[no-untyped-def]
        original(self, filename, arcname, compress_type, compresslevel)
        raise OSError("backup interrupted")

    monkeypatch.setattr(zipfile.ZipFile, "write", interrupted)
    destination = tmp_path / "backups"
    with pytest.raises(OSError, match="backup interrupted"):
        backup(ws, destination)
    assert list(destination.glob("ema-backup-*.zip")) == []


def test_gc_grace_allows_upload_then_slot(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "client", 2025)
    source = tmp_path / "source.txt"
    source.write_text("synthetic upload")
    sha = ws.add_file("client", source)
    ws.gc()
    assert ws.set_slot(job, "input", sha).file_sha == sha
    ws.remove_version(job, "input", 1)
    with ws.connect() as db:
        db.execute("UPDATE files SET added_at=0 WHERE sha=?", (sha,))
    ws.gc()
    with ws.connect() as db:
        assert db.execute("SELECT 1 FROM files WHERE sha=?", (sha,)).fetchone() is None


def test_reupload_refreshes_gc_grace_and_restores_missing_file(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "client", 2025)
    source = tmp_path / "source.txt"
    source.write_text("synthetic repeated upload")
    sha = ws.add_file("client", source)
    with ws.connect() as db:
        relative = db.execute("SELECT relative_path FROM files WHERE sha=?", (sha,)).fetchone()[0]
        db.execute("UPDATE files SET added_at=0 WHERE sha=?", (sha,))

    assert ws.add_file("client", source) == sha
    ws.gc()
    assert ws.set_slot(job, "input", sha).file_sha == sha

    ws.remove_version(job, "input", 1)
    with ws.connect() as db:
        db.execute("UPDATE files SET added_at=0 WHERE sha=?", (sha,))
    ws.path(relative).unlink()
    assert ws.add_file("client", source) == sha
    assert ws.path(relative).read_bytes() == source.read_bytes()
    ws.gc()
    assert ws.set_slot(job, "input", sha).file_sha == sha


def test_schema_one_migrates_to_two() -> None:
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE files (sha TEXT)")
        db.execute("INSERT INTO files VALUES ('recent')")
        db.execute("CREATE TABLE runs (id TEXT)")
        db.execute("CREATE TABLE outputs (id TEXT)")
        db.execute("PRAGMA user_version = 1")
        db.commit()
        workspace_schema.migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
        assert "added_at" in {row[1] for row in db.execute("PRAGMA table_info(files)")}
        assert db.execute("SELECT added_at FROM files").fetchone()[0] > 0
        assert "cancel_requested" in {row[1] for row in db.execute("PRAGMA table_info(runs)")}


def test_gitignore_keeps_client_folders_ignored() -> None:
    root = Path(__file__).resolve().parents[2]
    for relative in (
        "tests/golden/reference/example.pdf",
        "tests/client-data/file.pdf",
        "outputs/file.xlsx",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", relative], cwd=root, check=False
        )
        assert result.returncode == 0, relative
    package = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", "src/ema/core/workspace/__init__.py"],
        cwd=root,
        check=False,
    )
    assert package.returncode == 1
