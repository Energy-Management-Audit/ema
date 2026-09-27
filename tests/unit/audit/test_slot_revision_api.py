"""Deleting a document version uses the slot revision exposed with that version."""

from pathlib import Path

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.core.jobs import create_job
from ema.core.workspace import Workspace


def test_slot_versions_expose_revision_and_delete_rejects_stale(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    source = tmp_path / "document.txt"
    source.write_text("first", encoding="utf-8")
    ws.set_slot(job, "dossier/document.txt", ws.add_file("synthetic", source))
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"), base_url="http://127.0.0.1:8766"
    )
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    headers = {"X-Ema-CSRF": token}
    path = f"/jobs/{job}/slots/dossier/document.txt/versions"
    versions = client.get(path).json()
    revision = versions[0]["slot_revision"]
    assert isinstance(revision, int)
    source.write_text("second", encoding="utf-8")
    ws.set_slot(job, "dossier/document.txt", ws.add_file("synthetic", source))
    stale = client.request(
        "DELETE", f"{path}/1", json={"confirm": True, "on_revision": revision}, headers=headers
    )
    assert stale.status_code == 409
    assert stale.json()["type"] == "urn:ema:error:stale_revision"
    assert client.get(path).json()[0]["slot_revision"] == revision + 1
