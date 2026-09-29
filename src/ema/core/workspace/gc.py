"""Remove unreferenced workspace files after their grace period."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ema.core.workspace.lock import workspace_lock
from ema.core.workspace.references import annex_uses_file, evidence_uses_file, upload_uses_file

if TYPE_CHECKING:
    from ema.core.workspace import Workspace


def collect_garbage(ws: Workspace) -> None:
    with workspace_lock(ws.root), ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        referenced_outputs = {
            str(row[0]) for row in db.execute("SELECT relative_path FROM outputs")
        }
        running = {str(row[0]) for row in db.execute("SELECT id FROM runs WHERE state='running'")}
        for row in db.execute("SELECT relative_path FROM jobs"):
            output_dir = ws.path(str(row[0])) / "outputs"
            for path in output_dir.glob("*"):
                if (
                    path.is_file()
                    and path.relative_to(ws.root).as_posix() not in referenced_outputs
                    and path.name.split("-", 1)[0] not in running
                    and (not path.name.startswith(".") or path.stat().st_mtime < time.time() - 3600)
                ):
                    path.unlink()
        rows = db.execute(
            "SELECT sha,client_slug,relative_path FROM files WHERE added_at<?",
            (time.time() - 3600,),
        ).fetchall()
        for row in rows:
            used = db.execute(
                "SELECT 1 FROM slot_versions sv JOIN jobs j ON j.id=sv.job_id "
                "WHERE sv.file_sha=? AND j.client_slug=? LIMIT 1",
                (row["sha"], row["client_slug"]),
            ).fetchone()
            if used is None:
                used = db.execute(
                    "SELECT 1 FROM run_inputs WHERE file_sha=? AND client_slug=? LIMIT 1",
                    (row["sha"], row["client_slug"]),
                ).fetchone()
            if used is None and not (
                evidence_uses_file(db, str(row["sha"]), str(row["client_slug"]))
                or annex_uses_file(db, str(row["sha"]), str(row["client_slug"]))
                or upload_uses_file(db, str(row["sha"]), str(row["client_slug"]))
            ):
                ws.path(str(row["relative_path"])).unlink(missing_ok=True)
                db.execute(
                    "DELETE FROM files WHERE sha=? AND client_slug=?",
                    (row["sha"], row["client_slug"]),
                )
