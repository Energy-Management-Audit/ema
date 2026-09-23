"""Persist revisions of job settings."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ema.core.errors import EmaError

if TYPE_CHECKING:
    from ema.core.workspace import Workspace


def write_settings(ws: Workspace, job: str, values: dict[str, object]) -> None:
    with ws.connect() as db:
        cursor = db.execute(
            "UPDATE jobs SET settings=?,settings_revision=settings_revision+1 "
            "WHERE id=? AND deleted=0",
            (json.dumps(values), job),
        )
        if cursor.rowcount == 0:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
