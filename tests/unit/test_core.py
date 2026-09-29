"""S1 integration contracts, using only synthetic files."""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.workspace_jobs import create_job

from ema import __version__
from ema.api import create_app
from ema.core import config
from ema.core.backup import backup, restore
from ema.core.errors import EmaError
from ema.core.jobs import StageOutcome, cancel, list_jobs, recover, run_stage, status
from ema.core.logging import capture_child
from ema.core.resources import resource_path
from ema.core.workspace import Workspace


def wait_run(ws: Workspace, job: str) -> dict[str, object]:
    for _ in range(200):
        result = status(ws, job)
        if result.state != "running":
            return result.runs[-1]
        time.sleep(0.01)
    pytest.fail("stage did not finish")


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "workspace")


def file(ws: Workspace, tmp_path: Path, content: str) -> str:
    source = tmp_path / f"{content}.txt"
    source.write_text(content, encoding="utf-8")
    return ws.add_file("client", source)


def test_job_round_trip_and_backup(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", 2025)
    first = file(ws, tmp_path, "first")
    second = file(ws, tmp_path, "second")
    ws.set_slot(job, "invoices", first)
    ws.set_slot(job, "invoices", second)
    ws.remove_version(job, "invoices", 1)

    def stage(ctx):  # type: ignore[no-untyped-def]
        assert ctx.read_slot("invoices").file_sha == second
        artifact = ctx.artifact_dir() / "result.json"
        artifact.write_text('{"ok":true}', encoding="utf-8")
        ctx.save_output(artifact, "result.json")
        return StageOutcome()

    run_stage(ws, job, "extract", stage)
    assert wait_run(ws, job)["publication"] == "current"
    archive = backup(ws, tmp_path / "backups")
    restored = Workspace(restore(archive, tmp_path / "restored"))
    assert list_jobs(restored) == list_jobs(ws)
    with restored.connect() as db:
        assert {entry[0] for entry in restored.referenced_files(db)} == {
            entry[0] for entry in ws.referenced_files(db)
        }
    assert status(restored, job).state == "ready"
    env = {**os.environ, "EMA_WORKSPACE": str(restored.root)}
    executable = Path(sys.executable).parent / "ema"
    listed = subprocess.run(
        [executable, "job", "list"], env=env, capture_output=True, text=True, check=True
    )
    assert json.loads(listed.stdout)[0]["id"] == job
    shown = subprocess.run(
        [executable, "job", "status", job], env=env, capture_output=True, text=True, check=True
    )
    assert json.loads(shown.stdout)["state"] == "ready"


def test_publish_detects_slot_and_setting_changes(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", 2025)
    first = file(ws, tmp_path, "first")
    second = file(ws, tmp_path, "second")
    ws.set_slot(job, "input", first)
    ws.write_settings(job, {"provider": "one"})
    read = threading.Event()
    release = threading.Event()

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.read_slot("input")
        ctx.read_setting("provider")
        read.set()
        assert release.wait(2)
        (ctx.artifact_dir() / "result").write_text("result", encoding="utf-8")
        return StageOutcome()

    run_stage(ws, job, "extract", stage)
    assert read.wait(2)
    ws.set_slot(job, "input", second)
    ws.write_settings(job, {"provider": "two"})
    release.set()
    assert wait_run(ws, job)["publication"] == "stale"


def test_stage_failure_and_item_failure(ws: Workspace) -> None:
    job = create_job(ws, "audit", "client", 2025)

    def broken(ctx):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic failure")

    run_stage(ws, job, "extract", broken)
    assert wait_run(ws, job)["state"] == "failed"
    log = next(ws.root.glob("clients/client/jobs/*/log.jsonl")).read_text(encoding="utf-8")
    assert "Traceback" in log

    def partial(ctx):  # type: ignore[no-untyped-def]
        return StageOutcome(item_failures=["item 2"])

    run_stage(ws, job, "retry", partial)
    result = wait_run(ws, job)
    assert result["state"] == "ready"
    assert json.loads(result["outcome"])["item_failures"] == ["item 2"]


def test_cancel(ws: Workspace) -> None:
    job = create_job(ws, "audit", "client", 2025)
    read = threading.Event()

    def slow(ctx):  # type: ignore[no-untyped-def]
        read.set()
        for _ in range(200):
            if ctx.cancelled():
                return StageOutcome()
            time.sleep(0.005)
        pytest.fail("cancellation was not observed")

    run_stage(ws, job, "extract", slow)
    assert read.wait(2)
    cancel(ws, job)
    assert wait_run(ws, job)["state"] == "cancelled"


def test_recovery_and_interrupted_delete(ws: Workspace) -> None:
    job = create_job(ws, "invoices", "client", 2025)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO runs (id,job_id,stage,owner,state,started_at) "
            "VALUES ('run',?,'x','dead','running','now')",
            (job,),
        )
        db.execute("UPDATE jobs SET state='running' WHERE id=?", (job,))
    recover(ws)
    assert status(ws, job).runs[0]["error"] == "interrupted"
    with ws.connect() as db:
        event = db.execute("SELECT type,payload FROM job_events WHERE job_id=?", (job,)).fetchone()
    assert event["type"] == "stage_failed"
    assert json.loads(event["payload"])["code"] == "interrupted"
    with ws.connect() as db:
        path = ws.job_path(db, job)
        db.execute("UPDATE jobs SET deleted=1 WHERE id=?", (job,))
    ws.finish_deletes()
    assert not path.exists()
    assert list_jobs(ws) == []


def test_content_addressing_and_gc(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", 2025)
    sha = file(ws, tmp_path, "same")
    assert file(ws, tmp_path, "same") == sha
    ws.set_slot(job, "one", sha)
    ws.set_slot(job, "two", sha)
    ws.remove_version(job, "one", 1)
    ws.gc()
    with ws.connect() as db:
        assert len(db.execute("SELECT * FROM files").fetchall()) == 1
        assert ws.path(db.execute("SELECT relative_path FROM files").fetchone()[0]).exists()


def test_restore_rejects_tamper(ws: Workspace, tmp_path: Path) -> None:
    archive = backup(ws, tmp_path / "backups")
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(tampered, "w") as output:
        for name in original.namelist():
            output.writestr(name, b"bad" if name == "ema.sqlite" else original.read(name))
    with pytest.raises(EmaError, match=r"ema\.sqlite"):
        restore(tampered, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_child_stderr(ws: Workspace) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import sys;sys.stderr.write('child error\\n')"],
        stderr=subprocess.PIPE,
        text=True,
    )
    with ws.app_log() as handle:
        capture_child(process, handle)
    process.wait()
    assert "child error" in (ws.root / "logs" / "ema.jsonl").read_text(encoding="utf-8")


def test_resource_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert resource_path("templates", "example.docx").parts[-3:] == (
        "resources",
        "templates",
        "example.docx",
    )
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_path("test") == tmp_path / "resources" / "test"


def test_health_host_and_origin(ws: Workspace) -> None:
    client = TestClient(create_app(ws, 8000), base_url="http://127.0.0.1:8000")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 421
    assert client.get("/health", headers={"origin": "http://evil.example"}).status_code == 403


def test_backup_while_deleting_job(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", 2025)
    ws.set_slot(job, "input", file(ws, tmp_path, "concurrent"))
    gate = threading.Barrier(3)
    result: dict[str, Path] = {}
    errors: list[BaseException] = []

    def do_backup() -> None:
        try:
            gate.wait()
            result["archive"] = backup(ws, tmp_path / "backups")
        except BaseException as exc:
            errors.append(exc)

    def do_delete() -> None:
        try:
            gate.wait()
            ws.delete_job(job)
        except BaseException as exc:
            errors.append(exc)

    workers = [threading.Thread(target=do_backup), threading.Thread(target=do_delete)]
    for worker in workers:
        worker.start()
    gate.wait()
    for worker in workers:
        worker.join(timeout=5)
    assert not errors
    assert all(not worker.is_alive() for worker in workers)
    restored = Workspace(restore(result["archive"], tmp_path / "restored"))
    assert len(list_jobs(restored)) in (0, 1)
    with restored.connect() as db:
        for relative, sha, size in restored.referenced_files(db):
            data = restored.path(relative).read_bytes()
            assert hashlib.sha256(data).hexdigest() == sha
            assert len(data) == size


def test_cli_version_and_help() -> None:
    executable = Path(sys.executable).parent / "ema"
    result = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, encoding="utf-8", check=True
    )
    assert result.stdout.strip() == __version__
    result = subprocess.run(
        [executable, "--help"], capture_output=True, text=True, encoding="utf-8", check=True
    )
    assert "workspace" in result.stdout and "backup" in result.stdout


def test_gc_keeps_file_used_by_completed_run(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", 2025)
    sha = file(ws, tmp_path, "retained")
    ws.set_slot(job, "input", sha)

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.read_slot("input")
        return StageOutcome()

    run_stage(ws, job, "extract", stage)
    assert wait_run(ws, job)["state"] == "ready"
    ws.remove_version(job, "input", 1)
    ws.gc()
    with ws.connect() as db:
        row = db.execute("SELECT relative_path FROM files WHERE sha=?", (sha,)).fetchone()
        assert row is not None
        assert ws.path(row["relative_path"]).exists()


def test_publish_failure_does_not_leave_run_running(ws: Workspace) -> None:
    job = create_job(ws, "invoices", "client", 2025)

    def invalid(ctx):  # type: ignore[no-untyped-def]
        return object()

    run_stage(ws, job, "extract", invalid)
    assert wait_run(ws, job)["state"] == "failed"
    assert "Traceback" in next(ws.root.glob("clients/client/jobs/*/log.jsonl")).read_text(
        encoding="utf-8"
    )


def test_recovery_preserves_live_runner(ws: Workspace) -> None:
    job = create_job(ws, "invoices", "client", 2025)
    started = threading.Event()
    finish = threading.Event()

    def stage(ctx):  # type: ignore[no-untyped-def]
        started.set()
        assert finish.wait(2)
        return StageOutcome()

    run_stage(ws, job, "extract", stage)
    assert started.wait(2)
    recover(Workspace(ws.root))
    assert status(ws, job).state == "running"
    finish.set()
    assert wait_run(ws, job)["state"] == "ready"


def test_interface_errors_hide_detail(ws: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(ws, 8000, launch_code="synthetic-launch-code")

    @app.get("/broken")
    def broken() -> None:
        raise EmaError("broken", "Eroare vizibilă.", "private diagnostic detail")

    client = TestClient(app, base_url="http://127.0.0.1:8000")
    assert client.get("/broken").status_code == 403
    assert client.post("/session", json={"code": "synthetic-launch-code"}).status_code == 200
    response = client.get("/broken")
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert "private diagnostic detail" not in response.text
    assert "private diagnostic detail" not in (ws.root / "logs" / "ema.jsonl").read_text(
        encoding="utf-8"
    )
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    executable = Path(sys.executable).parent / "ema"
    result = subprocess.run(
        [executable, "job", "status", "missing"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode != 0
    assert "Lucrarea nu există." in result.stderr
    assert "missing" not in result.stderr


def test_generic_read_set_extends_without_jobs_changes(ws: Workspace) -> None:
    job = create_job(ws, "audit", "client", 2025)
    with ws.connect() as db:
        db.execute("CREATE TABLE review_item (id TEXT PRIMARY KEY, revision INTEGER NOT NULL)")
        db.execute("INSERT INTO review_item VALUES ('one',1)")
    read = threading.Event()
    finish = threading.Event()

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.record_read("review_item", "one", 1)
        read.set()
        assert finish.wait(2)
        return StageOutcome()

    run_stage(ws, job, "review", stage)
    assert read.wait(2)
    with ws.connect() as db:
        db.execute("UPDATE review_item SET revision=2 WHERE id='one'")
    finish.set()
    assert wait_run(ws, job)["publication"] == "stale"


def test_slot_versions_do_not_reuse_removed_number(ws: Workspace, tmp_path: Path) -> None:
    job = create_job(ws, "invoices", "client", 2025)
    sha = file(ws, tmp_path, "versioned")
    assert ws.set_slot(job, "input", sha).version == 1
    assert ws.set_slot(job, "input", sha).version == 2
    ws.remove_version(job, "input", 2)
    assert ws.set_slot(job, "input", sha).version == 3


def test_workspace_discovery_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        f"workspace = {json.dumps(str(tmp_path / 'configured'))}\n", encoding="utf-8"
    )
    monkeypatch.setattr(config, "user_config_dir", lambda _name, **_kwargs: str(config_dir))
    monkeypatch.delenv("EMA_WORKSPACE", raising=False)
    assert config.workspace_path() == tmp_path / "configured"
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path / "env"))
    assert config.workspace_path() == tmp_path / "env"
