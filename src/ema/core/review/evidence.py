"""Read a persisted evidence record without exposing workspace paths."""

from __future__ import annotations

import json

from ema.core.errors import EmaError
from ema.core.review.models import Evidence
from ema.core.workspace import Workspace


def get_evidence(ws: Workspace, evidence_id: str) -> Evidence:
    with ws.connect() as db:
        row = db.execute("SELECT data FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if row is None:
        raise EmaError("evidence_missing", "Dovada nu există.", evidence_id)
    data = json.loads(row["data"])
    if "provenance" not in data:
        data["provenance"] = {"online": "online", "calc": "calculated", "manual": "manual"}.get(
            data["method"], "document"
        )
    return Evidence.model_validate(data)


def get_evidence_view(ws: Workspace, evidence_id: str) -> tuple[Evidence, str | None]:
    with ws.connect() as db:
        row = db.execute(
            "SELECT e.data, (SELECT v.original_name FROM slot_versions v "
            "WHERE v.job_id=e.job_id AND v.file_sha=json_extract(e.data, '$.file_sha') "
            "AND v.original_name IS NOT NULL ORDER BY v.version DESC LIMIT 1) AS file_name "
            "FROM evidence e WHERE e.id=?",
            (evidence_id,),
        ).fetchone()
    if row is None:
        raise EmaError("evidence_missing", "Dovada nu există.", evidence_id)
    data = json.loads(row["data"])
    if "provenance" not in data:
        data["provenance"] = {"online": "online", "calc": "calculated", "manual": "manual"}.get(
            data["method"], "document"
        )
    return Evidence.model_validate(data), row["file_name"]
