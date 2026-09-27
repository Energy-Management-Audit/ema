"""Run activity exposes its existing timestamps through one status read."""

from pathlib import Path

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.core.jobs import create_job
from ema.core.workspace import Workspace


def test_status_has_finished_and_running_run_timestamps(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"),
        base_url="http://127.0.0.1:8766",
    )
    assert client.post("/session", json={"code": "synthetic-code"}).status_code == 200
    with ws.connect() as db:
        db.execute(
            "INSERT INTO runs(id,job_id,stage,owner,state,started_at,ended_at) "
            "VALUES ('finished',?,'intake','test','ready',?,?)",
            (job, "2026-09-27T08:00:00Z", "2026-09-27T08:01:00Z"),
        )
        db.execute(
            "INSERT INTO runs(id,job_id,stage,owner,state,started_at) "
            "VALUES ('running',?,'read','test','running','2026-09-27T08:02:00Z')",
            (job,),
        )
    runs = client.get(f"/jobs/{job}/status").json()["runs"]
    assert [(run["started_at"], run["ended_at"]) for run in runs] == [
        ("2026-09-27T08:00:00Z", "2026-09-27T08:01:00Z"),
        ("2026-09-27T08:02:00Z", None),
    ]
