"""Output rows carry their display name, creation time, run and stage (B5)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.core.jobs import StageContext, StageOutcome, create_job, run_stage, status, subscribe
from ema.core.jobs.outputs import get_output, list_outputs
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def _stage(ctx: StageContext) -> StageOutcome:
    for name in ("Prelucrare-date.xlsx", "PIEE-draft.docx"):
        path = ctx.artifact_dir() / name
        path.write_bytes(b"PK synthetic")
        ctx.save_output(path, name)
    return StageOutcome()


def test_outputs_carry_name_created_at_run_and_stage(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "synthetic", 2026)
    run = run_stage(ws, job, "piee_generate", _stage)
    for _ in subscribe(ws, job):
        pass
    ended = next(item for item in status(ws, job).runs if item["id"] == run)
    with ws.connect() as db:
        ended_at = db.execute("SELECT ended_at FROM runs WHERE id=?", (run,)).fetchone()[0]
    assert ended["state"] == "ready"
    rows = list_outputs(ws, job)
    assert [row["name"] for row in rows] == ["Prelucrare-date.xlsx", "PIEE-draft.docx"]
    assert all(row["run_id"] == run and row["stage"] == "piee_generate" for row in rows)
    assert all(row["created_at"] == ended_at for row in rows)
    metadata, _relative = get_output(ws, job, rows[1]["id"])
    assert metadata["download_name"] == "PIEE-draft.docx"

    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url=BASE)
    client.post("/session", json={"code": "code"})
    body = client.get(f"/jobs/{job}/outputs").json()
    assert {key for key in body[0]} >= {"name", "created_at", "run_id", "stage"}
    assert body[1]["name"] == "PIEE-draft.docx"
