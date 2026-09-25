"""SQLite schema shared by workspace and jobs."""

import sqlite3
import time

SCHEMA_VERSION = 9


def migrate(db: sqlite3.Connection) -> None:  # noqa: C901
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
        version = 2
    if version == 2:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE fields (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, key TEXT NOT NULL,
                revision INTEGER NOT NULL, data TEXT NOT NULL,
                UNIQUE(job_id, key), FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE evidence (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, data TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE decisions (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, field_id TEXT NOT NULL,
                at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, data TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE approvals (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, output_id TEXT NOT NULL,
                readiness_hash TEXT NOT NULL, on_decision TEXT,
                at TEXT NOT NULL, actor TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            PRAGMA user_version = 3;
            COMMIT;
        """)
        version = 3
    if version == 3:
        db.executescript("""
            BEGIN IMMEDIATE;
            ALTER TABLE outputs ADD COLUMN kind TEXT NOT NULL DEFAULT 'draft';
            ALTER TABLE decisions ADD COLUMN seq INTEGER NOT NULL DEFAULT 0;
            UPDATE decisions SET seq=rowid;
            CREATE UNIQUE INDEX decisions_seq ON decisions(seq);
            PRAGMA user_version = 4;
            COMMIT;
        """)
        version = 4
    if version == 4:
        db.executescript("""
            BEGIN IMMEDIATE;
            ALTER TABLE outputs ADD COLUMN seq INTEGER NOT NULL DEFAULT 0;
            UPDATE outputs SET seq=rowid;
            CREATE UNIQUE INDEX outputs_seq ON outputs(seq);
            PRAGMA user_version = 5;
            COMMIT;
        """)
        version = 5
    if version == 5:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE section_states (
                job_id TEXT NOT NULL, section_id TEXT NOT NULL,
                revision INTEGER NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (job_id, section_id),
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE audit_materials (
                job_id TEXT NOT NULL, kind TEXT NOT NULL,
                present INTEGER NOT NULL, source TEXT NOT NULL,
                PRIMARY KEY (job_id, kind),
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            PRAGMA user_version = 6;
            COMMIT;
        """)
        version = 6
    if version == 6:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE client_memory (
                kind TEXT NOT NULL, identifier TEXT NOT NULL, legal_name TEXT NOT NULL,
                tax_id TEXT, job_id TEXT NOT NULL, decision_id TEXT NOT NULL,
                PRIMARY KEY (kind, identifier, decision_id),
                FOREIGN KEY(job_id) REFERENCES jobs(id),
                FOREIGN KEY(decision_id) REFERENCES decisions(id)
            );
            CREATE INDEX client_memory_lookup ON client_memory(kind, identifier);
            PRAGMA user_version = 7;
            COMMIT;
        """)
        version = 7
    if version == 7:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE agent_sessions (
                job_id TEXT NOT NULL, section TEXT NOT NULL, state TEXT NOT NULL,
                PRIMARY KEY(job_id, section), FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE llm_calls (
                id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, section TEXT NOT NULL,
                provider TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
                input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
                estimated_cost_usd REAL NOT NULL, duration_ms INTEGER NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            PRAGMA user_version = 8;
            COMMIT;
        """)
        version = 8
    if version == 8:
        # Historical migration tests model only the tables under test; real v8
        # workspaces always have jobs, while those minimal fixtures do not.
        has_jobs = (
            db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
            is not None
        )
        backfill = (
            "INSERT OR IGNORE INTO clients(id) "
            "SELECT DISTINCT client_slug FROM jobs WHERE type != 'reporting';"
            if has_jobs
            else ""
        )
        db.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE job_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                run_id TEXT, stage TEXT, type TEXT NOT NULL, at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX job_events_job_seq ON job_events(job_id, seq);
            CREATE TABLE clients (
                id TEXT PRIMARY KEY, name TEXT, cui TEXT, caen TEXT,
                sites_json TEXT NOT NULL DEFAULT '[]',
                contacts_json TEXT NOT NULL DEFAULT '[]',
                revision INTEGER NOT NULL DEFAULT 1, anaf_refreshed_at TEXT
            );
            CREATE TABLE client_uploads (
                client_id TEXT NOT NULL, sha TEXT NOT NULL,
                original_name TEXT NOT NULL, kind TEXT NOT NULL,
                size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(client_id, sha)
            );
            CREATE TABLE anaf_snapshots (
                client_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                retrieved_at TEXT, source_url TEXT, payload_json TEXT, sha TEXT
            );
            CREATE TABLE reporting_runs (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
                years_json TEXT NOT NULL, client_ids_json TEXT NOT NULL,
                state TEXT NOT NULL, exceptions_json TEXT NOT NULL DEFAULT '[]',
                output_id TEXT
            );
        """
            + backfill
            + """
            PRAGMA user_version = 9;
            COMMIT;
        """
        )
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
            CREATE TABLE fields (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, key TEXT NOT NULL,
                revision INTEGER NOT NULL, data TEXT NOT NULL,
                UNIQUE(job_id, key), FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE evidence (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, data TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE decisions (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, field_id TEXT NOT NULL,
                at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, data TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE approvals (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, output_id TEXT NOT NULL,
                readiness_hash TEXT NOT NULL, on_decision TEXT,
                at TEXT NOT NULL, actor TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            PRAGMA user_version = 3;
            COMMIT;
    """)
    migrate(db)
