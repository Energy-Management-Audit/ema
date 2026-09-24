"""Delete job rows after its folder has been removed."""

import sqlite3


def delete_job_rows(db: sqlite3.Connection, job_id: str) -> None:
    for table in ("run_inputs", "run_files", "run_reads"):
        db.execute(
            f"DELETE FROM {table} WHERE run_id IN (SELECT id FROM runs WHERE job_id=?)",
            (job_id,),
        )
    for table in (
        "approvals",
        "client_memory",
        "decisions",
        "section_states",
        "audit_materials",
        "agent_sessions",
        "llm_calls",
        "evidence",
        "fields",
        "outputs",
        "runs",
        "slot_versions",
        "slots",
    ):
        db.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))
    db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
