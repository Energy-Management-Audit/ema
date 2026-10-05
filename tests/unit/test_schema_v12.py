"""Recorded upload names survive the v11 workspace migration."""

import sqlite3
from pathlib import Path

from tests.workspace_jobs import create_job

from ema.core.workspace import Workspace, upload_name
from ema.core.workspace.schema import SCHEMA_VERSION, migrate
from ema.piee import workflow


def test_migration_moves_only_recorded_names(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    with ws.connect() as db:
        db.execute("ALTER TABLE slot_versions DROP COLUMN original_name")
        db.execute("PRAGMA user_version = 11")
        for slot, version, sha, origin, converted_from in (
            ("invoices/0001", 1, "invoice", "invoice.pdf", None),
            ("cover/photo", 1, "photo", "photo.png", None),
            ("cover/photo", 2, "converted", "converted", "photo"),
            ("anexa", 1, "api", "upload", None),
            ("questionnaire", 1, "cli", "upload", None),
        ):
            db.execute("INSERT OR IGNORE INTO slots(job_id,name) VALUES (?,?)", (job, slot))
            db.execute(
                "INSERT INTO slot_versions VALUES (?,?,?,?,?,?)",
                (job, slot, version, sha, origin, converted_from),
            )
        db.execute(
            "INSERT INTO client_uploads VALUES (?,?,?,?,?,?)",
            ("synthetic", "api", "api.xlsx", "xlsx", 10, "2026-01-01"),
        )
        migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 13
        rows = db.execute(
            "SELECT slot,version,origin,original_name FROM slot_versions ORDER BY slot,version"
        ).fetchall()
        assert [(r["slot"], r["origin"], r["original_name"]) for r in rows] == [
            ("anexa", "upload", "api.xlsx"),
            ("cover/photo", "upload", "photo.png"),
            ("cover/photo", "converted", "photo.png"),
            ("invoices/0001", "upload", "invoice.pdf"),
            ("questionnaire", "upload", None),
        ]


def test_schema_one_migrates_through_v12() -> None:
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE files (sha TEXT)")
        db.execute("INSERT INTO files VALUES ('recent')")
        db.execute("CREATE TABLE runs (id TEXT)")
        db.execute("CREATE TABLE outputs (id TEXT)")
        db.execute("CREATE TABLE jobs (id TEXT, client_slug TEXT, type TEXT)")
        db.execute(
            "CREATE TABLE slot_versions (job_id TEXT, slot TEXT, version INTEGER, "
            "file_sha TEXT, origin TEXT, converted_from TEXT)"
        )
        db.execute("PRAGMA user_version = 1")
        db.commit()
        migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert "added_at" in {row[1] for row in db.execute("PRAGMA table_info(files)")}
        assert db.execute("SELECT added_at FROM files").fetchone()[0] > 0
        assert "cancel_requested" in {row[1] for row in db.execute("PRAGMA table_info(runs)")}


def test_upload_name_and_slot_lookup(tmp_path: Path) -> None:
    assert upload_name(r"folder\nested/bad?:name.pdf") == "bad__name.pdf"
    assert upload_name("... ") is None
    assert upload_name("a" * 300) == "a" * 255
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"synthetic")
    sha = ws.add_file("synthetic", path)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO client_uploads VALUES (?,?,?,?,?,?)",
            ("synthetic", sha, "recorded.pdf", "pdf", 9, "2026-01-01"),
        )
    assert ws.set_slot(job, "dossier/one", sha).original_name == "recorded.pdf"
    assert (
        ws.set_slot(job, "dossier/two", sha, original_name="explicit.pdf").original_name
        == "explicit.pdf"
    )
    other = tmp_path / "other.pdf"
    other.write_bytes(b"other")
    other_sha = ws.add_file("synthetic", other)
    assert ws.set_slot(job, "dossier/three", other_sha).original_name is None
    assert ws.list_versions(job, "dossier/two")[0].original_name == "explicit.pdf"


def test_set_prelucrare_uses_upload_record(tmp_path: Path, monkeypatch) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "piee", "synthetic", 2026)
    source = tmp_path / "source.xlsx"
    source.write_bytes(b"synthetic")
    sha = ws.add_file("synthetic", source)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO client_uploads VALUES (?,?,?,?,?,?)",
            ("synthetic", sha, "recorded.xlsx", "xlsx", 9, "2026-01-01"),
        )
    monkeypatch.setattr(workflow, "import_prelucrare", lambda _path: None)
    monkeypatch.setattr(workflow, "prelucrare_state", lambda _ws, _job: {})
    workflow.set_prelucrare(ws, job, sha)
    assert ws.list_versions(job, "prelucrare")[0].original_name == "recorded.xlsx"
