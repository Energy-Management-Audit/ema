"""Human confirmation guards for values read from photos."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import uuid

from ema.core.errors import EmaError
from ema.core.review.models import Actor, Decision, Field
from ema.core.review.store import load_field
from ema.core.workspace import Workspace


def require_human(field: Field, actor: Actor) -> None:
    if field.needs_confirmation and actor != "user":
        raise EmaError("human_required", "Confirmarea umană este necesară.", field.id)


def accept_batch(
    ws: Workspace, job: str, field_ids_with_revisions: list[tuple[str, int]], actor: Actor
) -> list[Decision]:
    from ema.core.review.fields import _decide_in_tx  # noqa: PLC0415

    batch_id = uuid.uuid4().hex
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        fields = [load_field(db, job, field_id) for field_id, _ in field_ids_with_revisions]
        for field in fields:
            if field.needs_confirmation:
                raise EmaError(
                    "confirmation_individual",
                    "Valorile citite de pe fotografii se confirmă una câte una.",
                    field.id,
                )
        return [
            _decide_in_tx(
                db,
                job,
                field_id,
                "accept",
                revision,
                actor,
                value=None,
                alternative=None,
                batch_id=batch_id,
            )
            for field_id, revision in field_ids_with_revisions
        ]
