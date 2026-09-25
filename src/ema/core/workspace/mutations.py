"""Revision-bound workspace mutation kept outside the filesystem façade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ema.core.errors import EmaError

if TYPE_CHECKING:
    from ema.core.workspace import Workspace


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
            raise EmaError("job_unavailable", "Lucrarea lipsește sau rulează.", job)
    ws.finish_deletes()
