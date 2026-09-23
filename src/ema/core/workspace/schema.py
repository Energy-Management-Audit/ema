"""SQLite schema shared by workspace and jobs."""

import sqlite3
import time

SCHEMA_VERSION = 2


def migrate(db: sqlite3.Connection) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"Workspace schema {version} is newer than Ema")
    if version == SCHEMA_VERSION:
        return
    if version == 1:
        db.execute("BEGIN IMMEDIATE")
        db.execute("ALTER TABLE files ADD COLUMN added_at REAL NOT NULL DEFAULT 0")
        db.execute("UPDATE files SET added_at=?", (time.time(),))
        db.execute("ALTER TABLE runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
        db.execute("PRAGMA user_version = 2")
        return
    db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, type TEXT NOT NULL, client_slug TEXT NOT NULL,
                year INTEGER, relative_path TEXT NOT NULL, state TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0,
                settings TEXT NOT NULL DEFAULT '{}', settings_revision INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE files (
                sha TEXT NOT NULL, client_slug TEXT NOT NULL, relative_path TEXT NOT NULL,
                size INTEGER NOT NULL, added_at REAL NOT NULL,
                PRIMARY KEY (sha, client_slug)
            );
            CREATE TABLE slots (
                job_id TEXT NOT NULL, name TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                active_version INTEGER, next_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (job_id, name),
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );
            CREATE TABLE slot_versions (
                job_id TEXT NOT NULL, slot TEXT NOT NULL, version INTEGER NOT NULL,
                file_sha TEXT NOT NULL, origin TEXT NOT NULL, converted_from TEXT,
                PRIMARY KEY (job_id, slot, version),
                FOREIGN KEY (job_id, slot) REFERENCES slots(job_id, name)
            );
            CREATE TABLE runners (
                id TEXT PRIMARY KEY, host TEXT NOT NULL, pid INTEGER NOT NULL,
                process_start REAL NOT NULL, heartbeat REAL NOT NULL
            );
            CREATE TABLE runs (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, stage TEXT NOT NULL,
                owner TEXT NOT NULL, state TEXT NOT NULL, publication TEXT,
                fingerprint TEXT, outcome TEXT, error TEXT,
                started_at TEXT NOT NULL, ended_at TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );
            CREATE TABLE run_reads (
                run_id TEXT NOT NULL, table_name TEXT NOT NULL, row_id TEXT NOT NULL,
                revision INTEGER NOT NULL, PRIMARY KEY (run_id, table_name, row_id)
            );
            CREATE TABLE run_inputs (
                run_id TEXT NOT NULL, client_slug TEXT NOT NULL, file_sha TEXT NOT NULL,
                PRIMARY KEY (run_id, client_slug, file_sha)
            );
            CREATE TABLE run_files (
                run_id TEXT NOT NULL, relative_path TEXT NOT NULL, sha TEXT NOT NULL,
                size INTEGER NOT NULL, PRIMARY KEY (run_id, relative_path)
            );
            CREATE TABLE outputs (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, run_id TEXT NOT NULL,
                relative_path TEXT NOT NULL, sha TEXT NOT NULL, size INTEGER NOT NULL
            );
            PRAGMA user_version = 2;
            COMMIT;
    """)
