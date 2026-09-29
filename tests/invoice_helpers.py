"""Test-only batch identity undo adapter."""

from ema.core.errors import EmaError
from ema.core.jobs import JobId
from ema.core.review import fields, undo
from ema.core.review.models import Decision
from ema.core.workspace import Workspace
from ema.invoices.batch_identity import KEY


def undo_client(ws: Workspace, job: JobId, decision_id: str) -> Decision:
    field = next((item for item in fields(ws, job) if item.key == KEY), None)
    if field is None:
        raise EmaError("client_missing", "Clientul lotului nu a fost identificat.", job)
    with ws.connect() as db:
        row = db.execute(
            "SELECT 1 FROM decisions WHERE id=? AND job_id=? AND field_id=?",
            (decision_id, job, field.id),
        ).fetchone()
    if row is None:
        raise EmaError(
            "client_decision_missing", "Decizia clientului lotului lipseşte.", decision_id
        )
    return undo(ws, job, decision_id, "user")
