"""A stage refused by an EmaError says so in its stage_failed event; others stay opaque."""

from __future__ import annotations

import json
from pathlib import Path

from tests.workspace_jobs import create_job

from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, run_stage, status, subscribe
from ema.core.workspace import Workspace


def _failed_payload(ws: Workspace, job: str, error: Exception) -> dict[str, object]:
    def stage(ctx: StageContext) -> StageOutcome:
        raise error

    run = run_stage(ws, job, "audit_render", stage)
    for _ in subscribe(ws, job):
        pass
    assert next(item for item in status(ws, job).runs if item["id"] == run)["error"] == str(error)
    with ws.connect() as db:
        row = db.execute(
            "SELECT payload FROM job_events WHERE run_id=? AND type='stage_failed'", (run,)
        ).fetchone()
    return json.loads(row["payload"])


def test_ema_error_carries_code_and_message(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "audit", "synthetic", 2026)
    error = EmaError("audit_markers", "Raportul final are câmpuri necompletate.", "ch3.flux")
    assert _failed_payload(ws, job, error) == {
        "code": "audit_markers",
        "message": "Raportul final are câmpuri necompletate.",
    }


def test_other_exception_stays_stage_failed(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "audit", "synthetic", 2026)
    assert _failed_payload(ws, job, ValueError("internal detail")) == {"code": "stage_failed"}
