"""The overview reads cross-workflow state without losing jobs on readiness errors."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.workspace_jobs import create_job

from ema.api import create_app
from ema.core.jobs import activity
from ema.core.review import overview
from ema.core.workspace import Workspace


def test_activity_uses_newest_job_run_and_decision_timestamp(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "audit", "client-exemplu", 2026)
    with ws.connect() as db:
        db.execute("UPDATE jobs SET created_at='2026-09-26T00:00:00Z' WHERE id=?", (job,))
        db.execute(
            "INSERT INTO runs(id,job_id,stage,owner,state,started_at,ended_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                "run-1",
                job,
                "readings",
                "user",
                "ready",
                "2026-09-27T08:00:00Z",
                "2026-09-27T09:00:00Z",
            ),
        )
        db.execute(
            "INSERT INTO decisions(id,job_id,field_id,at,data) VALUES (?,?,?,?,?)",
            ("decision-1", job, "field-1", "2026-09-27T10:00:00Z", "{}"),
        )
    with ws.connect() as db:
        assert activity(db)[job] == "2026-09-27T10:00:00Z"


def test_overview_route_orders_and_isolates_readiness(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    audit = create_job(ws, "audit", "client-doi", 2026)
    invoice = create_job(ws, "invoices", "client-exemplu", 2025)
    piee = create_job(ws, "piee", "client-exemplu", 2026)
    create_job(ws, "reporting", "reporting", None)
    with ws.connect() as db:
        db.execute("UPDATE clients SET name='Exemplu Energie SA' WHERE id='client-exemplu'")
        db.execute("UPDATE jobs SET created_at='2026-09-27T08:00:00+00:00' WHERE id=?", (audit,))
        db.execute("UPDATE jobs SET created_at='2026-09-27T09:00:00+00:00' WHERE id=?", (invoice,))
        db.execute("UPDATE jobs SET created_at='2026-09-27T10:00:00+00:00' WHERE id=?", (piee,))
        db.execute(
            "INSERT INTO approvals(id,job_id,output_id,readiness_hash,at,actor) "
            "VALUES (?,?,?,?,?,?)",
            ("approval-1", audit, "output-1", "hash", "2026-09-27T11:00:00+00:00", "user"),
        )
        db.execute(
            "INSERT INTO outputs(id,job_id,run_id,relative_path,sha,size,kind) "
            "VALUES (?,?,?,?,?,?,?)",
            ("invoice-final", invoice, "run-1", "synthetic.xlsx", "sha", 10, "final"),
        )
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"), base_url="http://127.0.0.1:8766"
    )
    assert client.post("/session", json={"code": "synthetic-code"}).status_code == 200
    response = client.get("/jobs/overview")
    assert response.status_code == 200
    rows = response.json()
    assert {row["id"] for row in rows} == {audit, invoice, piee}
    assert rows[0]["id"] == piee
    by_id = {row["id"]: row for row in rows}
    assert by_id[invoice]["readiness_error"] == "invoices_missing"
    assert by_id[invoice]["final_ok"] is None
    assert by_id[invoice]["finalized"] is True
    assert by_id[audit]["approved_at"] == "2026-09-27T11:00:00+00:00"
    assert by_id[audit]["finalized"] is True
    assert by_id[piee]["client_name"] == "Exemplu Energie SA"
    assert by_id[piee]["blocking"] is not None


def test_overview_keeps_one_snapshot_when_a_job_is_created_between_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    existing = create_job(ws, "piee", "client-exemplu", 2025)
    created: list[str] = []
    original_activity = overview.activity

    def activity_then_create(db: sqlite3.Connection) -> dict[str, str]:
        updated = original_activity(db)
        created.append(create_job(ws, "piee", "client-exemplu", 2026))
        return updated

    monkeypatch.setattr(overview, "activity", activity_then_create)
    client = TestClient(
        create_app(ws, 8767, launch_code="synthetic-code"), base_url="http://127.0.0.1:8767"
    )
    assert client.post("/session", json={"code": "synthetic-code"}).status_code == 200
    response = client.get("/jobs/overview")
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {existing}
    assert len(created) == 1


def test_overview_uses_created_at_when_activity_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "client-exemplu", 2025)
    monkeypatch.setattr(overview, "activity", lambda _db: {})
    client = TestClient(
        create_app(ws, 8768, launch_code="synthetic-code"), base_url="http://127.0.0.1:8768"
    )
    assert client.post("/session", json={"code": "synthetic-code"}).status_code == 200
    response = client.get("/jobs/overview")
    assert response.status_code == 200
    row = next(item for item in response.json() if item["id"] == job)
    assert row["updated_at"] == row["created_at"]
