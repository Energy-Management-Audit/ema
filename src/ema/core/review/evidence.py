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
