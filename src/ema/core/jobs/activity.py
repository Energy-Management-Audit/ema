"""Last activity for non-deleted jobs in the caller's database snapshot."""

import sqlite3


def activity(db: sqlite3.Connection) -> dict[str, str]:
    rows = db.execute(
        "SELECT job_id, MAX(at) AS updated_at FROM ("
        "SELECT id AS job_id, created_at AS at FROM jobs WHERE deleted=0 "
        "UNION ALL SELECT r.job_id, r.started_at FROM runs r "
        "JOIN jobs j ON j.id=r.job_id WHERE j.deleted=0 "
        "UNION ALL SELECT r.job_id, r.ended_at FROM runs r "
        "JOIN jobs j ON j.id=r.job_id WHERE j.deleted=0 AND r.ended_at IS NOT NULL "
        "UNION ALL SELECT d.job_id, d.at FROM decisions d "
        "JOIN jobs j ON j.id=d.job_id WHERE j.deleted=0"
        ") GROUP BY job_id"
    ).fetchall()
    return {str(row["job_id"]): str(row["updated_at"]) for row in rows}
