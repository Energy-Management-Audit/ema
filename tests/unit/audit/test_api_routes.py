"""Audit work routes enforce job type, typed inputs, and revision conflicts."""

from pathlib import Path

from fastapi.testclient import TestClient
from tests.workspace_jobs import create_job

from ema.api import create_app
from ema.core.workspace import Workspace


def test_audit_work_routes_reject_other_job_types_and_bad_inputs(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    audit = create_job(ws, "audit", "synthetic", 2026)
    piee = create_job(ws, "piee", "synthetic", 2026)
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"), base_url="http://127.0.0.1:8766"
    )
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    headers = {"X-Ema-CSRF": token}
    for path in ("documents", "outline"):
        response = client.get(f"/jobs/{piee}/audit/{path}")
        assert response.status_code == 400
        assert response.json()["type"] == "urn:ema:error:wrong_job_type"
    for path, body in (
        (f"/jobs/{piee}/audit/notes/ch1", {"text": "x", "on_revision": 0}),
        (f"/jobs/{piee}/audit/deadline", {"deadline": None, "on_revision": 0}),
    ):
        response = client.put(path, json=body, headers=headers)
        assert response.status_code == 400
        assert response.json()["type"] == "urn:ema:error:wrong_job_type"
    invalid = client.put(
        f"/jobs/{audit}/audit/deadline",
        json={"deadline": "tomorrow", "on_revision": 0},
        headers=headers,
    )
    assert invalid.status_code == 422
    too_long = client.put(
        f"/jobs/{audit}/audit/notes/ch1",
        json={"text": "a" * 2001, "on_revision": 0},
        headers=headers,
    )
    assert too_long.status_code == 422
    good = client.put(
        f"/jobs/{audit}/audit/notes/ch1",
        json={"text": "Check", "on_revision": 0},
        headers=headers,
    )
    assert good.status_code == 200 and good.json()["revision"] == 1
    stale = client.put(
        f"/jobs/{audit}/audit/notes/ch1",
        json={"text": "Old", "on_revision": 0},
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["type"] == "urn:ema:error:stale_revision"
