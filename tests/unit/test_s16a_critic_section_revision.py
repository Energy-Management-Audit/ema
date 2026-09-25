"""A stale section confirmation must not overwrite a newer decision."""

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.audit.catalogue import CATALOGUE
from ema.core.jobs import create_job
from ema.core.workspace import Workspace


def test_stale_na_confirmation_cannot_override_newer_section_state(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"),
        base_url="http://127.0.0.1:8766",
    )
    csrf = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    headers = {"x-ema-csrf": csrf}
    section = CATALOGUE[0].id
    initial = client.get(f"/jobs/{job}/sections").json()[0]
    assert initial["revision"] == 0
    assert (
        client.patch(
            f"/jobs/{job}/sections/{section}",
            json={"status": "n/a", "reason": "older proposal", "confirm": True, "on_revision": 0},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/jobs/{job}/sections/{section}",
            json={"status": "n/a", "reason": "newer decision", "confirm": True, "on_revision": 1},
            headers=headers,
        ).status_code
        == 200
    )
    replay = client.patch(
        f"/jobs/{job}/sections/{section}",
        json={"status": "n/a", "reason": "older proposal", "confirm": True, "on_revision": 0},
        headers=headers,
    )
    assert replay.status_code == 409
    assert replay.json() == {
        "type": "urn:ema:error:stale_revision",
        "title": "Secțiunea s-a modificat între timp.",
        "status": 409,
    }
    assert client.get(f"/jobs/{job}/sections").json()[0]["reason"] == "newer decision"
