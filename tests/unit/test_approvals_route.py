"""Final approvals are readable, newest first (B6)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.workspace_jobs import create_job

from ema.api import create_app
from ema.core.jobs import StageContext, StageOutcome, run_stage, subscribe
from ema.core.review import approve_final
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def _final(ctx: StageContext) -> StageOutcome:
    path = ctx.artifact_dir() / "PIEE-final.docx"
    path.write_bytes(b"PK final")
    ctx.save_output(path, "PIEE-final.docx", kind="final")
    return StageOutcome()


def test_approvals_are_listed_newest_first(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "synthetic", 2026)
    run_stage(ws, job, "piee_word", _final)
    for _ in subscribe(ws, job):
        pass
    with ws.connect() as db:
        output = db.execute("SELECT id FROM outputs WHERE job_id=?", (job,)).fetchone()[0]
    first = approve_final(ws, job, output, "hash-1", "user")
    second = approve_final(ws, job, output, "hash-2", "user")
    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url=BASE)
    client.post("/session", json={"code": "code"})
    response = client.get(f"/jobs/{job}/approvals")
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [second.id, first.id]
    assert set(body[0]) == {
        "id",
        "job_id",
        "output_id",
        "readiness_hash",
        "on_decision",
        "at",
        "actor",
        "exported_at",
    }
    assert body[0]["exported_at"] is None
    assert body[0]["output_id"] == output and body[0]["readiness_hash"] == "hash-2"
    missing = client.get("/jobs/nope/approvals")
    assert missing.status_code == 404
    assert missing.json()["type"] == "urn:ema:error:job_missing"
