"""New client and reporting routes precede their dynamic-id neighbours."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.unit.energy_data.test_annex_index import annex

from ema.api import create_app
from ema.clients.registry import create_client
from ema.core.jobs import create_job
from ema.core.workspace import Workspace


def _session(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"), base_url="http://127.0.0.1:8766"
    )
    csrf = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    return client, {"x-ema-csrf": csrf}


def test_route_order_shapes_and_validation(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    client, headers = _session(ws)
    assert client.get("/clients/overview").json() == []
    assert client.post("/clients/annexes", headers=headers).status_code == 422
    path = tmp_path / "annex.xlsx"
    annex(path)
    with path.open("rb") as stream:
        reply = client.post(
            "/clients/annexes",
            headers=headers,
            files=[
                (
                    "files",
                    (
                        path.name,
                        stream,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                )
            ],
        )
    assert reply.status_code == 200
    imported = reply.json()["imported"][0]
    assert imported["year"] == 2025
    assert client.get("/clients/overview").json()[0]["id"] == imported["client_id"]
    assert (
        client.get(f"/clients/{imported['client_id']}/profile").json()["identification"]["source"]
        == "annex"
    )
    assert client.get("/clients/INVALID!/profile").status_code == 400
    assert client.get("/clients/unknown/profile").status_code == 404
    too_many = [("files", (f"{n}.xlsx", b"bad", "application/octet-stream")) for n in range(101)]
    assert client.post("/clients/annexes", headers=headers, files=too_many).status_code == 413


def test_reporting_list_and_preview_gate(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    person = create_client(ws, "Exemplu", "12345678")
    job = create_job(ws, "reporting", "reporting", 2025)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO reporting_runs(id,job_id,years_json,client_ids_json,state) "
            "VALUES (?,?,?,?,?)",
            ("run-one", job, "[2025]", f'["{person["id"]}"]', "running"),
        )
    client, _ = _session(ws)
    assert client.get("/reporting/runs").json()[0]["id"] == "run-one"
    waiting = client.get("/reporting/runs/run-one/preview")
    assert waiting.status_code == 409
    assert waiting.json()["type"] == "urn:ema:error:run_not_ready"
    assert client.get("/reporting/runs/missing/preview").status_code == 404
