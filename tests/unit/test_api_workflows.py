"""Shared HTTP use cases persist real state across requests."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openpyxl import Workbook

from ema.api import create_app
from ema.core.jobs import StageOutcome, create_job, run_stage, subscribe
from ema.core.workspace import Workspace
from ema.invoices.batch_identity import KEY as BATCH_CLIENT_KEY

BASE = "http://127.0.0.1:8766"


def _session(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    return client, {"X-Ema-CSRF": token}


def test_client_anaf_settings_and_reporting_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    ws = Workspace(tmp_path)
    client, headers = _session(ws)
    identity = client.post(
        "/clients",
        json={"name": "Synthetic", "cui": "RO123456"},
        headers=headers,
    )
    assert identity.status_code == 201
    client_id = identity.json()["id"]
    assert client.get(f"/clients/{client_id}/sites").json() == []
    assert client.get(f"/clients/{client_id}/contacts").json() == []
    assert client.get(f"/clients/{client_id}").json()["name"] == "Synthetic"
    monkeypatch.setattr(
        "ema.clients.anaf.web.fetch_bytes",
        lambda *_args, **_kwargs: (
            "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva",
            "application/json",
            b'{"found":[{"date_generale":{"cui":123456}}]}',
        ),
    )
    refreshed = client.post(f"/clients/{client_id}/anaf/refresh", json={}, headers=headers)
    assert refreshed.status_code == 200
    with ws.connect() as db:
        assert (
            db.execute(
                "SELECT status FROM anaf_snapshots WHERE client_id=?", (client_id,)
            ).fetchone()[0]
            == "complete"
        )
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0

    monkeypatch.delenv("EMA_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("EMA_OPENAI_API_KEY", raising=False)
    settings = client.get("/settings").json()
    assert not settings["providers"]["gemini"]["present"]
    assert "key" not in json.dumps(settings).lower()
    assert (
        client.post(
            "/settings/providers/gemini/test",
            json={},
            headers=headers,
        ).json()["status"]
        == "no_key"
    )
    denied = client.put(
        "/settings",
        json={"gemini_api_key": "synthetic"},
        headers=headers,
    )
    assert denied.status_code == 400 and denied.json()["type"] == "urn:ema:error:key_not_allowed"

    workbook = Workbook()
    buffer = io.BytesIO()
    workbook.save(buffer)
    uploaded = client.post(
        f"/clients/{client_id}/files",
        files={"file": ("synthetic.xlsx", buffer.getvalue())},
        headers=headers,
    )
    assert uploaded.status_code == 201
    monkeypatch.setattr(
        "ema.reporting.runs.generate",
        lambda _paths, _years: SimpleNamespace(exceptions=[]),
    )
    monkeypatch.setattr(
        "ema.reporting.runs.write_report",
        lambda _result, path: path.write_bytes(b"synthetic workbook"),
    )
    started = client.post(
        "/reporting/runs",
        json={"years": [2025], "client_ids": [client_id]},
        headers=headers,
    )
    assert started.status_code == 202
    run_id = started.json()["id"]
    with ws.connect() as db:
        job = db.execute("SELECT job_id FROM reporting_runs WHERE id=?", (run_id,)).fetchone()[0]
    list(subscribe(ws, job))
    completed = client.get(f"/reporting/runs/{run_id}")
    assert completed.status_code == 200
    assert completed.json()["state"] == "ready"
    assert completed.json()["output_id"]
    assert completed.json()["years"] == [2025]


def test_invoice_http_confirm_and_final_export(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ws = Workspace(tmp_path)
    client, headers = _session(ws)
    client_id = client.post(
        "/clients",
        json={"name": "Synthetic"},
        headers=headers,
    ).json()["id"]
    job = create_job(ws, "invoices", client_id, None)
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    digest = ws.add_file(client_id, source)
    ws.set_slot(job, "invoices/0001", digest)

    def field(value: str) -> dict[str, object]:
        return {"value": value, "status": "extracted", "message": None, "evidence": []}

    rows = [
        {
            "source_path": "synthetic.pdf",
            "slot": "invoices/0001",
            "file_sha": digest,
            "status": "exportable",
            "issues": [],
            "reason": None,
            "metadata": {},
            "drafts": [
                {
                    "supplier": "SUPPLIER",
                    "source_filename": "synthetic.pdf",
                    "issues": [],
                    "metadata": {},
                    "fields": {
                        "client_name": field("ALPHA SRL"),
                        "client_tax_id": field("RO123"),
                        "location_identifier": field("POD0001"),
                    },
                }
            ],
        }
    ]

    def extract(ctx):  # type: ignore[no-untyped-def]
        ctx.read_slots("invoices")
        (ctx.artifact_dir() / "outcomes.json").write_text(json.dumps(rows))
        return StageOutcome()

    run_stage(ws, job, "invoices", extract)
    list(subscribe(ws, job))
    candidate = client.get(f"/jobs/{job}/invoices/identity")
    assert candidate.status_code == 200
    assert candidate.json()["candidate"]["client_id"] == client_id
    with ws.connect() as db:
        revision = db.execute(
            "SELECT revision FROM fields WHERE job_id=? AND key=?", (job, BATCH_CLIENT_KEY)
        ).fetchone()[0]
    refused = client.post(
        f"/jobs/{job}/invoices/identity",
        json={"client_id": client_id, "on_revision": revision, "confirm": False},
        headers=headers,
    )
    assert refused.status_code == 403
    confirmed = client.post(
        f"/jobs/{job}/invoices/identity",
        json={"client_id": client_id, "on_revision": revision, "confirm": True},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.json().get("type")
    assert confirmed.json()["confirmed"]
    stale = client.post(
        f"/jobs/{job}/invoices/identity",
        json={"client_id": client_id, "on_revision": revision, "confirm": True},
        headers=headers,
    )
    assert stale.status_code == 409
    monkeypatch.setattr("ema.invoices.exportable_drafts", lambda _payload: [object()])
    monkeypatch.setattr(
        "ema.invoices.OpenpyxlWorkbookExporter.export",
        lambda _self, _drafts, path: path.write_bytes(b"synthetic workbook"),
    )
    draft = client.post(
        f"/jobs/{job}/export/draft",
        json={"on_revision": client.get(f"/jobs/{job}").json()["revision"]},
        headers=headers,
    )
    assert draft.status_code == 200 and draft.json()["kind"] == "draft"
    next_draft = client.post(
        f"/jobs/{job}/export/draft",
        json={"on_revision": client.get(f"/jobs/{job}").json()["revision"]},
        headers=headers,
    )
    assert next_draft.status_code == 200
    assert next_draft.json()["output_id"] != draft.json()["output_id"]
    started = client.post(
        f"/jobs/{job}/stages/invoices_workbook",
        json={"on_revision": client.get(f"/jobs/{job}").json()["revision"]},
        headers=headers,
    )
    assert started.status_code == 202, started.json().get("type")
    list(subscribe(ws, job))
    final = next(
        item for item in client.get(f"/jobs/{job}/outputs").json() if item["kind"] == "final"
    )
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert checks["readiness"]["final_ok"]
    exported = client.post(
        f"/jobs/{job}/export",
        json={
            "final": True,
            "output_id": final["id"],
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
        },
        headers=headers,
    )
    assert exported.status_code == 200, exported.json().get("type")
    decision = client.get(f"/jobs/{job}/log").json()[-1]["id"]
    assert client.post(f"/jobs/{job}/log/{decision}/undo", headers=headers).status_code == 200
    stale_export = client.post(
        f"/jobs/{job}/export",
        json={
            "final": True,
            "output_id": final["id"],
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
        },
        headers=headers,
    )
    assert stale_export.status_code == 409


def test_reporting_run_recovers_interrupted_worker(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "reporting", "reporting", 2026)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO runs(id,job_id,stage,owner,state,started_at) "
            "VALUES ('dead-run',?,'reporting','dead','running','now')",
            (job,),
        )
        db.execute("UPDATE jobs SET state='running' WHERE id=?", (job,))
        db.execute(
            "INSERT INTO reporting_runs"
            "(id,job_id,years_json,client_ids_json,state) "
            "VALUES ('report-synthetic',?,'[2025]','[]','running')",
            (job,),
        )
    client, _headers = _session(ws)
    response = client.get("/reporting/runs/report-synthetic")
    assert response.status_code == 200
    assert response.json()["state"] == "failed"
    events = client.get(f"/jobs/{job}/events")
    assert "event: stage_failed" in events.text
