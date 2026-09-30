"""Revision-bound workspace mutation kept outside the filesystem façade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ema.core.errors import EmaError

if TYPE_CHECKING:
    from ema.core.workspace import Workspace


def remove_version(
    ws: Workspace, job: str, slot: str, version: int, *, on_revision: int | None = None
) -> None:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT active_version,revision FROM slots WHERE job_id=? AND name=?", (job, slot)
        ).fetchone()
        if on_revision is not None and (current is None or current["revision"] != on_revision):
            raise EmaError("stale_revision", "Fişierul a fost modificat.", "")
        cursor = db.execute(
            "DELETE FROM slot_versions WHERE job_id=? AND slot=? AND version=?",
            (job, slot, version),
        )
        if cursor.rowcount == 0:
            raise EmaError("version_missing", "Versiunea nu există.", f"{job}/{slot}/{version}")
        row = db.execute(
            "SELECT MAX(version) AS active FROM slot_versions WHERE job_id=? AND slot=?",
            (job, slot),
        ).fetchone()
        if current is not None and current["active_version"] != row["active"]:
            db.execute(
                "UPDATE slots SET active_version=?,revision=revision+1 WHERE job_id=? AND name=?",
                (row["active"], job, slot),
            )


def delete_job(ws: Workspace, job: str, *, on_revision: int | None = None) -> None:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT revision,state FROM jobs WHERE id=? AND deleted=0", (job,)
        ).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", "")
        if row["state"] == "running":
            raise EmaError("job_running", "Lucrarea rulează deja.", "")
        if on_revision is not None and row["revision"] != on_revision:
            raise EmaError("stale_revision", "Lucrarea a fost modificată.", "")
        cursor = db.execute(
            "UPDATE jobs SET deleted=1,revision=revision+1 "
            "WHERE id=? AND deleted=0 AND state!='running'",
            (job,),
        )
        if cursor.rowcount == 0:
            raise EmaError("job_unavailable", "Lucrarea lipseşte sau rulează.", job)
    ws.finish_deletes()
