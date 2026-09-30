"""Schema v10 preserves annex files and removes job annotations with jobs."""

import json
import sqlite3
import zipfile
from pathlib import Path

from tests.workspace_jobs import create_job

from ema.core.backup import backup
from ema.core.workspace import Workspace
from ema.core.workspace.schema import SCHEMA_VERSION, migrate


def _tables(db: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_v9_upgrade_and_fresh_workspace_have_both_tables(tmp_path: Path) -> None:
    old = Workspace(tmp_path / "old")
    job = create_job(old, "piee", "client-exemplu", 2025)
    source = tmp_path / "source.xlsx"
    source.write_bytes(b"synthetic source")
    sha = old.add_file("client-exemplu", source)
    with old.connect() as db:
        db.execute(
            "INSERT INTO fields(id,job_id,key,revision,data) VALUES (?,?,?,?,?)",
            ("field-1", job, "electricity", 2, '{"value":"12"}'),
        )
        db.execute(
            "INSERT INTO outputs(id,job_id,run_id,relative_path,sha,size,kind,seq) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("output-1", job, "run-1", "synthetic.docx", "output-sha", 4, "final", 1),
        )
        db.execute("DROP TABLE client_annexes")
        db.execute("DROP TABLE job_annotations")
        db.execute("ALTER TABLE approvals DROP COLUMN exported_at")
        db.execute("ALTER TABLE slot_versions DROP COLUMN original_name")
        db.execute("PRAGMA user_version = 9")
    upgraded = Workspace(tmp_path / "old")
    with upgraded.connect() as db:
        assert {"client_annexes", "job_annotations"} <= _tables(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("SELECT type,year FROM jobs WHERE id=?", (job,)).fetchone()[:] == (
            "piee",
            2025,
        )
        assert db.execute("SELECT revision,data FROM fields WHERE id='field-1'").fetchone()[:] == (
            2,
            '{"value":"12"}',
        )
        assert db.execute("SELECT kind,sha FROM outputs WHERE id='output-1'").fetchone()[:] == (
            "final",
            "output-sha",
        )
        assert db.execute("SELECT sha FROM files WHERE sha=?", (sha,)).fetchone()[0] == sha
        migrate(db)
    assert upgraded.file_path("client-exemplu", sha).read_bytes() == b"synthetic source"
    ws = Workspace(tmp_path / "fresh")
    with ws.connect() as db:
        assert {"client_annexes", "job_annotations"} <= _tables(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 12


def test_annex_only_file_survives_gc_and_enters_backup(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    source = tmp_path / "annex.xlsx"
    source.write_bytes(b"synthetic annex")
    sha = ws.add_file("client-exemplu", source)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO client_annexes VALUES (?,?,?,?,?)",
            ("client-exemplu", sha, 2026, "{}", "2026-09-27T00:00:00Z"),
        )
        db.execute("UPDATE files SET added_at=0 WHERE sha=?", (sha,))
        relative = str(
            db.execute("SELECT relative_path FROM files WHERE sha=?", (sha,)).fetchone()[0]
        )
        assert relative in {item[0] for item in ws.referenced_files(db)}
    ws.gc()
    assert ws.path(relative).exists()
    with zipfile.ZipFile(backup(ws, tmp_path / "backups")) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert relative in {item["path"] for item in manifest}


def test_delete_job_removes_annotations(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "client-exemplu", 2026)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO job_annotations(job_id,key,value,updated_at) VALUES (?,?,?,?)",
            (job, "deadline", "2026-12-31", "2026-09-27T00:00:00Z"),
        )
    ws.delete_job(job)
    ws.finish_deletes()
    with ws.connect() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM job_annotations WHERE job_id=?", (job,)).fetchone()[0]
            == 0
        )
