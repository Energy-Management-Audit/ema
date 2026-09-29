"""Slot validation and version views shared by interfaces."""

import re
from typing import Any

from ema.core.errors import EmaError
from ema.core.workspace import Workspace

_PIEE_SLOTS = {"anexa", "questionnaire", "prelucrare", "previous_piee"}


def validate_slot(job_type: str, slot: str) -> None:
    allowed = False
    if job_type == "piee":
        allowed = slot in _PIEE_SLOTS
    elif job_type == "invoices":
        allowed = re.fullmatch(r"invoices/[0-9]{4}", slot) is not None
    elif job_type == "audit":
        # cover/photo: the job's own cover photo, a one-file collection so its absence is read.
        if slot in {"anexa", "measures", "cover/photo"}:
            allowed = True
        else:
            prefix, separator, tail = slot.partition("/")
            parts = tail.split("/") if separator else []
            allowed = (
                prefix in {"dossier", "visit"}
                and 1 <= len(parts) <= 3
                and all(
                    1 <= len(part) <= 255
                    and part not in {".", ".."}
                    and "\\" not in part
                    and all(ord(char) >= 32 for char in part)
                    for part in parts
                )
            )
    if not allowed:
        raise EmaError("invalid_slot", "Numele fişierului este invalid.", "")


def slot_versions(ws: Workspace, job: str, slot: str) -> list[dict[str, Any]]:
    with ws.connect() as db:
        db.execute("BEGIN")
        if db.execute("SELECT 1 FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone() is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        rows = db.execute(
            "SELECT v.*,s.revision AS slot_revision FROM slot_versions v "
            "JOIN slots s ON s.job_id=v.job_id AND s.name=v.slot "
            "WHERE v.job_id=? AND v.slot=? ORDER BY v.version",
            (job, slot),
        ).fetchall()
    return [dict(row) for row in rows]
