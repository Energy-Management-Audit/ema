"""The v12 workspace migration gives each recorded AI call a nullable thinking count."""

from pathlib import Path

from tests.workspace_jobs import create_job

from ema.core.workspace import Workspace
from ema.core.workspace.schema import SCHEMA_VERSION, migrate


def test_migration_adds_a_nullable_thoughts_count(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    with ws.connect() as db:
        db.execute("ALTER TABLE llm_calls DROP COLUMN thoughts_tokens")
        db.execute("PRAGMA user_version = 12")
        db.execute(
            "INSERT INTO llm_calls(job_id,section,provider,model,prompt_version,input_tokens,"
            "output_tokens,estimated_cost_usd,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            (job, "draft:2-1", "gemini", "synthetic", "v1", 1, 1, 0.0, 1),
        )
        migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 13
        column = next(
            row for row in db.execute("PRAGMA table_info(llm_calls)") if row[1] == "thoughts_tokens"
        )
        assert (column[2], column[3]) == ("INTEGER", 0)
        assert db.execute("SELECT thoughts_tokens FROM llm_calls").fetchone()[0] is None
