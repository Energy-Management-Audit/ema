"""Human annotations kept outside stage read sets."""

from __future__ import annotations

from datetime import UTC, date, datetime

from ema.audit.catalogue import CATALOGUE
from ema.core.errors import EmaError
from ema.core.workspace import Workspace


def _write(
    ws: Workspace, job: str, key: str, value: str | None, on_revision: int, stale_title: str
) -> int:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        owner = db.execute("SELECT type FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone()
        if owner is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        if owner["type"] != "audit":
            raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
        row = db.execute(
            "SELECT revision FROM job_annotations WHERE job_id=? AND key=?", (job, key)
        ).fetchone()
        revision = int(row["revision"]) if row else 0
        if revision != on_revision:
            raise EmaError("stale_revision", stale_title, key)
        if value is None:
            db.execute("DELETE FROM job_annotations WHERE job_id=? AND key=?", (job, key))
            return 0
        db.execute(
            "INSERT INTO job_annotations (job_id,key,value,revision,updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(job_id,key) DO UPDATE SET "
            "value=excluded.value,revision=excluded.revision,updated_at=excluded.updated_at",
            (job, key, value, revision + 1, datetime.now(UTC).isoformat()),
        )
        return revision + 1


def put_note(
    ws: Workspace, job: str, section_id: str, text: str, on_revision: int
) -> dict[str, str | int]:
    if section_id not in {section.id for section in CATALOGUE}:
        raise EmaError("section_missing", "Secţiunea lipseşte.", section_id)
    revision = _write(
        ws,
        job,
        f"note:{section_id}",
        text or None,
        on_revision,
        "Notiţa a fost modificată între timp.",
    )
    return {"section_id": section_id, "text": text, "revision": revision}


def put_deadline(
    ws: Workspace, job: str, deadline: date | None, on_revision: int
) -> dict[str, str | int | None]:
    revision = _write(
        ws,
        job,
        "deadline",
        deadline.isoformat() if deadline else None,
        on_revision,
        "Termenul a fost modificat între timp.",
    )
    return {"deadline": deadline.isoformat() if deadline else None, "revision": revision}
