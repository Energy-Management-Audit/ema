"""Invoice upload use case: preserve names and allocate numbered slots."""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

from ema.clients.files import store_upload
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.workspace import Workspace, upload_name


def _safe_name(name: str) -> str | None:
    return upload_name(name)


def add_invoice_files(
    ws: Workspace,
    job: str,
    files: list[tuple[str, BinaryIO]],
    replace: str | None = None,
) -> dict[str, list[dict[str, str]]]:
    record = get_job(ws, job)
    if record["type"] != "invoices":
        raise EmaError("wrong_job_type", "Lucrarea nu este un lot de facturi.", "")
    if record["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", "")
    if replace is not None and re.fullmatch(r"invoices/[0-9]{4}", replace) is None:
        raise EmaError("invalid_slot", "Numele fişierului este invalid.", "")
    if not 1 <= len(files) <= 100 or (replace is not None and len(files) != 1):
        raise EmaError("validation_error", "Numărul fişierelor este invalid.", "")
    stored_files: list[tuple[str, str]] = []
    rejected: list[dict[str, str]] = []
    for name, stream in files:
        safe_name = _safe_name(name)
        if safe_name is None or Path(safe_name).suffix.lower() != ".pdf":
            rejected.append(
                {"file_name": safe_name or name, "code": "file_type", "reason": "Doar facturi PDF."}
            )
            continue
        try:
            stored = store_upload(ws, str(record["client_slug"]), stream, name)
        except EmaError as error:
            if error.code not in {"file_too_large", "file_type"}:
                raise
            rejected.append(
                {
                    "file_name": safe_name or name,
                    "code": error.code,
                    "reason": error.user_message_ro,
                }
            )
            continue
        stored_files.append((str(stored["name"]), str(stored["sha"])))
    return {"added": _attach_stored(ws, job, stored_files, replace), "rejected": rejected}


def _attach_stored(
    ws: Workspace, job: str, stored_files: list[tuple[str, str]], replace: str | None
) -> list[dict[str, str]]:
    added: list[dict[str, str]] = []
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT type,state FROM jobs WHERE id=? AND deleted=0", (job,)
        ).fetchone()
        if current is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        if current["type"] != "invoices":
            raise EmaError("wrong_job_type", "Lucrarea nu este un lot de facturi.", "")
        if current["state"] == "running":
            raise EmaError("job_running", "Lucrarea rulează deja.", "")
        if (
            replace is not None
            and db.execute(
                "SELECT 1 FROM slots WHERE job_id=? AND name=? AND active_version IS NOT NULL",
                (job, replace),
            ).fetchone()
            is None
        ):
            raise EmaError("invalid_slot", "Numele fişierului este invalid.", "")
        existing = db.execute(
            "SELECT name FROM slots WHERE job_id=? AND name LIKE 'invoices/%'", (job,)
        ).fetchall()
        next_number = (
            max(
                (
                    int(row["name"].rsplit("/", 1)[1])
                    for row in existing
                    if re.fullmatch(r"invoices/[0-9]{4}", row["name"])
                ),
                default=0,
            )
            + 1
        )
        for safe_name, sha in stored_files:
            slot = replace or f"invoices/{next_number:04d}"
            ws.set_slot_in_connection(db, job, slot, sha, origin="upload", original_name=safe_name)
            added.append({"slot": slot, "file_name": safe_name, "sha": sha})
            if replace is None:
                next_number += 1
    return added
