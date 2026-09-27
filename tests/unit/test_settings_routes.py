"""Status and problem contract for settings and backup routes."""

from pathlib import Path

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.core.jobs import create_job
from ema.core.settings import write_settings_values
from ema.core.workspace import Workspace


def _client(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"),
        base_url="http://127.0.0.1:8766",
    )
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    return client, {"x-ema-csrf": token}


def test_backup_route_statuses_and_settings_shape(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    create_job(ws, "audit", "synthetic", 2026)
    client, headers = _client(ws)
    settings = client.get("/settings")
    assert settings.status_code == 200
    assert settings.json()["workspace"] == str(ws.root)
    assert settings.json()["backup"]["due"] is True
    missing = client.post("/backups", json={}, headers=headers)
    assert (missing.status_code, missing.json()["type"]) == (
        409,
        "urn:ema:error:backup_dir_missing",
    )
    invalid = client.put("/settings", json={"backup_dir": "relative"}, headers=headers)
    assert (invalid.status_code, invalid.json()["type"]) == (
        400,
        "urn:ema:error:backup_dir_invalid",
    )
    folder = tmp_path / "backups"
    updated = client.put("/settings", json={"backup_dir": str(folder)}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["backup"]["dir"] == str(folder)
    made = client.post("/backups", json={}, headers=headers)
    assert made.status_code == 201
    assert Path(made.json()["path"]).is_file()
    assert client.get("/settings").json()["backup"]["due"] is False
    cleared = client.put("/settings", json={"backup_dir": None}, headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["backup"]["dir"] is None


def test_key_input_rejects_extra_and_malformed_json(tmp_path: Path) -> None:
    client, headers = _client(Workspace(tmp_path))
    for body in ({"key": "synthetic", "extra": True}, {"key": 12}, {}):
        reply = client.put("/settings/providers/gemini/key", json=body, headers=headers)
        assert reply.status_code == 422
        assert reply.json()["type"] == "urn:ema:error:validation_error"


def test_malformed_backup_timestamp_is_a_400(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    write_settings_values(ws, {"last_backup_at": "not-a-date"})
    client, _headers = _client(ws)
    response = client.get("/settings")
    assert response.status_code == 400
    assert response.json()["type"] == "urn:ema:error:settings_invalid"
