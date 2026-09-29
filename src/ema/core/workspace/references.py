"""Files that a workspace snapshot must preserve."""

import sqlite3


def referenced_files(db: sqlite3.Connection) -> list[tuple[str, str, int]]:
    rows = db.execute(
        "SELECT DISTINCT f.relative_path,f.sha,f.size FROM files f "
        "JOIN slot_versions v ON v.file_sha=f.sha "
        "JOIN jobs j ON j.id=v.job_id AND j.client_slug=f.client_slug "
        "WHERE j.deleted=0 UNION SELECT f.relative_path,f.sha,f.size FROM files f "
        "JOIN run_inputs i ON i.file_sha=f.sha AND i.client_slug=f.client_slug "
        "UNION SELECT f.relative_path,f.sha,f.size FROM files f "
        "JOIN evidence e ON json_extract(e.data,'$.file_sha')=f.sha "
        "JOIN jobs j ON j.id=e.job_id AND j.client_slug=f.client_slug "
        "UNION SELECT f.relative_path,f.sha,f.size FROM files f "
        "JOIN client_annexes a ON a.sha=f.sha AND a.client_id=f.client_slug "
        "UNION SELECT f.relative_path,f.sha,f.size FROM files f "
        "JOIN client_uploads u ON u.sha=f.sha AND u.client_id=f.client_slug "
        "UNION SELECT relative_path,sha,size FROM run_files "
        "UNION SELECT relative_path,sha,size FROM outputs"
    ).fetchall()
    return [(str(r[0]), str(r[1]), int(r[2])) for r in rows]


def evidence_uses_file(db: sqlite3.Connection, sha: str, client_slug: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM evidence e JOIN jobs j ON j.id=e.job_id "
            "WHERE json_extract(e.data,'$.file_sha')=? AND j.client_slug=? LIMIT 1",
            (sha, client_slug),
        ).fetchone()
        is not None
    )


def annex_uses_file(db: sqlite3.Connection, sha: str, client_slug: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM client_annexes WHERE sha=? AND client_id=? LIMIT 1",
            (sha, client_slug),
        ).fetchone()
        is not None
    )


def upload_uses_file(db: sqlite3.Connection, sha: str, client_slug: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM client_uploads WHERE sha=? AND client_id=? LIMIT 1",
            (sha, client_slug),
        ).fetchone()
        is not None
    )
