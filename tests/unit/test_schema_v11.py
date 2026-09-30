"""Delivered timestamps migrate without changing existing approvals or FieldSpec data."""

import sqlite3

from ema.core.workspace.schema import SCHEMA_VERSION, migrate


def test_v10_approval_survives_upgrade_with_null_delivery_timestamp():
    with sqlite3.connect(":memory:") as db:
        db.execute(
            "CREATE TABLE approvals (id TEXT PRIMARY KEY, job_id TEXT, output_id TEXT, "
            "readiness_hash TEXT, on_decision TEXT, at TEXT, actor TEXT)"
        )
        row = ("approved", "job", "output", "hash", None, "2026-09-29T00:00:00Z", "user")
        db.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?)", row)
        db.execute(
            "CREATE TABLE slot_versions (job_id TEXT, slot TEXT, version INTEGER, "
            "file_sha TEXT, origin TEXT, converted_from TEXT)"
        )
        db.execute("CREATE TABLE client_uploads (client_id TEXT, sha TEXT, original_name TEXT)")
        db.execute("CREATE TABLE jobs (id TEXT, client_slug TEXT)")
        db.execute("PRAGMA user_version=10")
        db.commit()
        migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 12
        assert db.execute("SELECT * FROM approvals").fetchone() == (*row, None)
        migrate(db)
        assert db.execute("SELECT * FROM approvals").fetchone() == (*row, None)
