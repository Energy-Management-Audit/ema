"""Annotations use their own revisions and do not enter stage read sets."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.audit.annotations import put_deadline, put_note
from ema.audit.outline import outline
from ema.core.errors import EmaError
from ema.core.jobs import StageOutcome, run_stage, subscribe
from ema.core.jobs.reads import run_current
from ema.core.review.section_transition import SectionState, Status
from ema.core.workspace import Workspace


def test_note_and_deadline_revision_and_clear(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    assert put_note(ws, job, "ch1", "Check source", 0)["revision"] == 1
    with pytest.raises(EmaError) as caught:
        put_note(ws, job, "ch1", "Stale", 0)
    assert caught.value.code == "stale_revision"
    assert outline(ws, job).nodes[0].note is not None
    assert put_note(ws, job, "ch1", "", 1)["revision"] == 0
    assert outline(ws, job).nodes[0].note is None
    assert put_deadline(ws, job, date(2026, 12, 1), 0)["revision"] == 1
    assert outline(ws, job).deadline.value == "2026-12-01"
    assert put_deadline(ws, job, None, 1)["revision"] == 0
    assert outline(ws, job).deadline.value is None


def test_annotation_does_not_stale_run_or_drafted_section(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    state = SectionState("ch1", Status.DRAFTED)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO section_states (job_id,section_id,revision,data) VALUES (?,?,?,?)",
            (job, "ch1", state.revision, json.dumps(state.payload())),
        )
    run = run_stage(ws, job, "read", lambda _ctx: StageOutcome())
    for _ in subscribe(ws, job):
        pass
    put_note(ws, job, "ch1", "Verify", 0)
    put_deadline(ws, job, date(2026, 12, 1), 0)
    with ws.connect() as db:
        assert run_current(db, run)
    chapter = next(node for node in outline(ws, job).nodes if node.id == "ch1")
    assert chapter.status == "drafted" and not chapter.stale
