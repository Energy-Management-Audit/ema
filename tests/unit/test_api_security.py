"""HTTP origin, session, CSRF, and human approval boundaries."""

from pathlib import Path

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.core.jobs import create_job
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def _session(client: TestClient) -> str:
    response = client.post("/session", json={"code": "synthetic-code"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "domain=" not in cookie
    return response.json()["csrf"]


def test_host_origin_cookie_and_csrf_on_all_media(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "audit", "synthetic", 2026)
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    paths = [
        "/jobs",
        f"/jobs/{job}/events",
        f"/jobs/{job}/preview.pdf",
        "/evidence/synthetic/page.png",
        f"/jobs/{job}/outputs/synthetic",
    ]
    for path in paths:
        host = client.get(path, headers={"Host": "evil.example"})
        assert host.status_code == 421
        assert host.json()["type"] == "urn:ema:error:invalid_host"
        origin = client.get(path, headers={"Origin": "http://evil.example"})
        assert origin.status_code == 403
        assert origin.json()["type"] == "urn:ema:error:invalid_origin"
        assert "access-control-allow-origin" not in origin.headers
    assert client.get("/jobs").json()["type"] == "urn:ema:error:session_required"
    token = _session(client)
    assert client.post("/session", json={"code": "synthetic-code"}).status_code == 403
    denied = client.post("/clients", json={"name": "Synthetic"})
    assert denied.status_code == 403
    assert denied.json()["type"] == "urn:ema:error:csrf_required"
    allowed = client.post("/clients", json={"name": "Synthetic"}, headers={"X-Ema-CSRF": token})
    assert allowed.status_code == 201


def test_problem_does_not_leak_detail_and_export_requires_confirmation(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "audit", "synthetic", 2026)
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    token = _session(client)
    headers = {"X-Ema-CSRF": token}
    missing = client.get("/jobs/secret-job-id")
    assert missing.status_code == 404
    assert set(missing.json()) == {"type", "title", "status"}
    assert "secret-job-id" not in missing.text
    refused = client.post(
        f"/jobs/{job}/export",
        headers=headers,
        json={"final": True, "output_id": "synthetic", "readiness_hash": "wrong", "confirm": False},
    )
    assert refused.status_code == 403
    assert refused.json()["type"] == "urn:ema:error:human_required"
    forged = client.post(
        f"/jobs/{job}/export",
        headers=headers,
        json={
            "final": True,
            "output_id": "synthetic",
            "readiness_hash": "wrong",
            "confirm": True,
            "actor": "system",
        },
    )
    assert forged.status_code == 422
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
