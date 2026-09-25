"""Immutable output metadata projections."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ema.core.errors import EmaError
from ema.core.jobs.reads import get_job
from ema.core.workspace import Workspace

MEDIA = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pdf": "application/pdf",
}


def list_outputs(ws: Workspace, job: str) -> list[dict[str, Any]]:
    get_job(ws, job)
    with ws.connect() as db:
        rows = db.execute(
            "SELECT id,seq,kind,relative_path,size,sha FROM outputs WHERE job_id=? ORDER BY seq",
            (job,),
        ).fetchall()
    return [_view(row, edited=_edited(ws, row)) for row in rows]


def get_output(ws: Workspace, job: str, output_id: str) -> tuple[dict[str, Any], str]:
    get_job(ws, job)
    with ws.connect() as db:
        row = db.execute(
            "SELECT id,seq,kind,relative_path,size,sha,run_id FROM outputs WHERE job_id=? AND id=?",
            (job, output_id),
        ).fetchone()
    if row is None:
        raise EmaError("output_missing", "Documentul nu există.", "")
    path = ws.path(str(row["relative_path"]))
    if not path.is_file():
        raise EmaError("output_missing", "Documentul nu există.", "")
    if _edited(ws, row):
        raise EmaError("output_stale", "Documentul a fost modificat extern.", "")
    view = _view(row, edited=False)
    stored_name = Path(str(row["relative_path"])).name
    prefix = f"{row['run_id']}-"
    original = stored_name.removeprefix(prefix)
    view["download_name"] = "".join(
        char if ord(char) >= 32 and char not in {"/", "\\"} else "_" for char in original
    )
    return view, str(row["relative_path"])


def _edited(ws: Workspace, row: Any) -> bool:
    path = ws.path(str(row["relative_path"]))
    if not path.is_file() or path.stat().st_size != int(row["size"]):
        return True
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest() != str(row["sha"])


def _view(row: Any, *, edited: bool) -> dict[str, Any]:
    relative = str(row["relative_path"])
    extension = "." + relative.rsplit(".", 1)[-1].lower() if "." in relative else ""
    media = MEDIA.get(extension)
    if media is None:
        raise EmaError("file_type", "Tipul documentului nu este acceptat.", "")
    return {
        "id": str(row["id"]),
        "version": int(row["seq"]),
        "kind": str(row["kind"]),
        "media_type": media,
        "size_bytes": int(row["size"]),
        "edited_externally": edited,
    }
