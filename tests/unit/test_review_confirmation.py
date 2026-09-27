"""Photo readings require one human decision per field."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ema.core.errors import EmaError
from ema.core.jobs import create_job
from ema.core.review import accept_batch, decide, fields, log, propose, undo
from ema.core.review.models import Photo
from ema.core.workspace import Workspace


def test_photo_region_validation() -> None:
    assert Photo(region=(0.1, 0.2, 0.8, 0.9)).region == (0.1, 0.2, 0.8, 0.9)
    for region in ((-0.1, 0.0, 0.5, 0.5), (0.8, 0.1, 0.2, 0.4), (0, 0, 1.1, 1)):
        with pytest.raises(ValidationError):
            Photo(region=region)


def test_reading_requires_individual_human_decision_and_undo(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    other = propose(ws, job, "ordinary", "ready", [], state="extracted")
    reading = propose(
        ws,
        job,
        "meter.panel.photo.voltage_ln.l1",
        230,
        [],
        state="extracted",
        needs_confirmation=True,
    )
    assert fields(ws, job, status="needs_confirmation") == [reading]
    for actor in ("ema", "agent"):
        for action in ("accept", "correct", "reject"):
            with pytest.raises(EmaError) as caught:
                decide(ws, job, reading.id, action, reading.revision, actor, value=231)
            assert caught.value.code == "human_required"
    with pytest.raises(EmaError) as caught:
        accept_batch(ws, job, [(other.id, other.revision), (reading.id, reading.revision)], "user")
    assert caught.value.code == "confirmation_individual"
    assert not log(ws, job)
    decision = decide(ws, job, reading.id, "accept", reading.revision, "user")
    assert not decision.after.needs_confirmation
    assert fields(ws, job, status="needs_confirmation") == []
    undo(ws, job, decision.id, "user")
    assert fields(ws, job, status="needs_confirmation")[0].id == reading.id


def test_new_vision_candidate_after_human_correction_requires_review(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    reading = propose(
        ws,
        job,
        "meter.panel.photo.voltage_ln.l1",
        230,
        [],
        state="extracted",
        needs_confirmation=True,
    )
    decide(ws, job, reading.id, "correct", reading.revision, "user", value=231)
    fresh = propose(ws, job, reading.key, 232, [], state="extracted", needs_confirmation=True)
    assert fresh.value == 231 and fresh.confidence == "conflict" and fresh.needs_confirmation
    with pytest.raises(EmaError) as caught:
        decide(ws, job, fresh.id, "accept", fresh.revision, "agent")
    assert caught.value.code == "human_required"
